"""
Diagnóstico read-only do ambiente para geração DOCX/PDF (sem instalar nada em requests HTTP).
"""

from __future__ import annotations

import importlib.util
import io
import logging
import platform
import sys
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from django.conf import settings

from documentos.services.libreoffice_resolve import resolve_libreoffice_binary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentEngineStatus:
    """Estado de um motor individual (útil para saída verbose)."""

    name: str
    available: bool
    detail: str = ""


@dataclass
class DocumentEnvironmentReport:
    os_name: str
    python_version: str
    docx_available: bool
    docx_missing_packages: list[str]
    pdf_available: bool
    preferred_pdf_engine: str | None
    available_pdf_engines: list[str]
    missing_pdf_engines: list[str]
    libreoffice_binary: str | None
    microsoft_word_available: bool
    weasyprint_available: bool
    simple_fallback_available: bool
    install_hints: list[str] = field(default_factory=list)
    engine_details: list[DocumentEngineStatus] = field(default_factory=list)


def _os_name() -> str:
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    if s == "linux":
        return "linux"
    return "unknown"


def _package_importable(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _check_docx() -> tuple[bool, list[str]]:
    missing: list[str] = []
    ok_docxtpl = _package_importable("docxtpl")
    ok_docx = _package_importable("docx")
    if not ok_docxtpl:
        missing.append("docxtpl")
    if not ok_docx:
        missing.append("python-docx")
    return (ok_docxtpl and ok_docx), missing


def _word_com_available() -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "não aplicável fora do Windows"
    if not _package_importable("win32com"):
        return False, "pywin32 não instalado"
    word: Any = None
    try:
        import win32com.client

        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        return True, "Word.Application respondeu"
    except Exception as exc:
        logger.debug("Word COM falhou no diagnóstico", exc_info=True)
        return False, str(exc)[:200]
    finally:
        if word is not None:
            try:
                word.Quit(SaveChanges=0)
            except Exception:
                logger.debug("Falha ao encerrar Word após diagnóstico", exc_info=True)


def _weasyprint_functional() -> tuple[bool, str]:
    if not _package_importable("weasyprint"):
        return False, "módulo weasyprint não importável"
    try:
        from weasyprint import HTML

        buf = io.BytesIO()
        HTML(string="<p>cv3</p>").write_pdf(buf)
        if len(buf.getvalue()) < 30:
            return False, "PDF gerado inválido ou vazio"
        return True, "render mínimo OK"
    except Exception as exc:
        logger.debug("WeasyPrint falhou no diagnóstico", exc_info=True)
        return False, str(exc)[:240]


def _fpdf2_available() -> bool:
    return _package_importable("fpdf")


def _build_install_hints(
    osn: str,
    *,
    missing: list[str],
    has_lo: bool,
    has_word: bool,
    has_weasy: bool,
) -> list[str]:
    hints: list[str] = []
    if not has_lo and "libreoffice" in missing:
        if osn == "windows":
            hints.append("Instale LibreOffice: winget install TheDocumentFoundation.LibreOffice")
            hints.append("Ou defina DOCUMENTOS_LIBREOFFICE_BINARY para soffice.exe")
        elif osn == "linux":
            hints.append("Instale LibreOffice: sudo apt update && sudo apt install -y libreoffice")
        elif osn == "macos":
            hints.append("Instale LibreOffice: brew install --cask libreoffice")
    if osn == "windows" and not has_word and "word_com" in missing:
        hints.append("Com Microsoft Word: python -m pip install docx2pdf pywin32")
    if not has_weasy and "weasyprint" in missing:
        hints.append(
            "WeasyPrint requer GTK/Pango/Cairo no Windows; veja documentação WeasyPrint ou use LibreOffice/Word."
        )
    hints.append("Diagnóstico: python manage.py documentos_check")
    return hints


def _preferred_engine(
    osn: str,
    *,
    word: bool,
    lo: bool,
    weasy: bool,
    simple: bool,
) -> str | None:
    if osn == "windows":
        order = ("word_com", "libreoffice", "weasyprint", "simple_fallback")
    elif osn == "linux":
        order = ("libreoffice", "weasyprint", "simple_fallback")
    else:
        order = ("libreoffice", "weasyprint", "word_com", "simple_fallback")
    avail = {
        "word_com": word,
        "libreoffice": lo,
        "weasyprint": weasy,
        "simple_fallback": simple,
    }
    for name in order:
        if avail.get(name):
            return name
    return None


def build_document_environment_report() -> DocumentEnvironmentReport:
    """Constrói um relatório completo sem efeitos laterais (exc. teste pontual WeasyPrint/Word)."""
    osn = _os_name()
    pyver = sys.version.split()[0]
    docx_ok, docx_missing = _check_docx()

    lo_bin = resolve_libreoffice_binary(verify_version=True)
    lo_ok = bool(lo_bin)

    word_ok, word_detail = _word_com_available()
    weasy_ok, weasy_detail = _weasyprint_functional()
    fpdf_ok = _fpdf2_available()
    simple_setting = getattr(settings, "DOCUMENTOS_SIMPLE_PDF_FALLBACK", False)
    simple_ok = fpdf_ok and bool(simple_setting)

    engines_avail: list[str] = []
    engines_missing: list[str] = []
    details: list[DocumentEngineStatus] = []

    def note(name: str, ok: bool, det: str = "") -> None:
        details.append(DocumentEngineStatus(name=name, available=ok, detail=det))
        if ok:
            engines_avail.append(name)
        else:
            engines_missing.append(name)

    note("word_com", word_ok, word_detail)
    note("libreoffice", lo_ok, lo_bin or "")
    note("weasyprint", weasy_ok, weasy_detail)
    note("simple_fallback", simple_ok, "fpdf2 + DOCUMENTOS_SIMPLE_PDF_FALLBACK" if fpdf_ok else "")

    preferred = _preferred_engine(
        osn, word=word_ok, lo=lo_ok, weasy=weasy_ok, simple=simple_ok,
    )
    pdf_ok = bool(preferred)

    hints = _build_install_hints(
        osn,
        missing=engines_missing,
        has_lo=lo_ok,
        has_word=word_ok,
        has_weasy=weasy_ok,
    )
    if docx_missing:
        hints.insert(0, "python -m pip install " + " ".join(docx_missing))
    if not pdf_ok:
        hints.append(
            "Nenhum motor PDF utilizável encontrado. Instale LibreOffice ou configure WeasyPrint / Word (Windows)."
        )

    return DocumentEnvironmentReport(
        os_name=osn,
        python_version=pyver,
        docx_available=docx_ok,
        docx_missing_packages=docx_missing,
        pdf_available=pdf_ok,
        preferred_pdf_engine=preferred,
        available_pdf_engines=list(engines_avail),
        missing_pdf_engines=list(engines_missing),
        libreoffice_binary=lo_bin,
        microsoft_word_available=word_ok,
        weasyprint_available=weasy_ok,
        simple_fallback_available=simple_ok,
        install_hints=hints,
        engine_details=details,
    )
