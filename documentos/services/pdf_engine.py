"""
Resolução do motor PDF (inclui modo `auto` por sistema operativo).

Não executa conversões — apenas decide a cadeia de tentativas e mensagens de apoio.
"""

from __future__ import annotations

import platform
import importlib.util
import threading
import time
from dataclasses import dataclass

from django.conf import settings

from documentos.services.adapters.word_pdf import is_word_pdf_available
from documentos.services.libreoffice_resolve import resolve_libreoffice_binary
from documentos.services.libreoffice_resolve import sys_platform_is_darwin
from documentos.services.libreoffice_resolve import sys_platform_is_linux


_availability_cache: dict[tuple[object, ...], tuple[list[str], list[str]]] = {}
_stable_probe_cache: dict[tuple[object, ...], dict[str, bool]] = {}
_availability_cache_lock = threading.Lock()

# Sondas cujo resultado não muda enquanto o processo vive: dependem de o
# software estar instalado (Word) ou de o módulo importar (WeasyPrint, fpdf).
# Repeti-las a cada janela custava caro à toa — o import que FALHA não fica em
# `sys.modules`, então toda janela refazia a maquinaria de import do WeasyPrint
# (e reimprimia o aviso de GTK ausente no Windows).
#
# `unoserver` e `libreoffice` ficam de fora de propósito: um serviço que sobe ou
# cai, e um binário instalado depois, precisam ser notados sem reiniciar o
# processo. São também as duas sondas baratas (HTTP curto e resolução de
# caminho, sem `--version`).
_STABLE_PROBE_NAMES = frozenset({"word_com", "weasyprint", "simple_fallback"})


def limpar_cache_de_sondas() -> None:
    """Zera as duas camadas de cache de sondagem (usada pelos testes)."""
    with _availability_cache_lock:
        _availability_cache.clear()
        _stable_probe_cache.clear()


@dataclass(frozen=True)
class PdfEngineResolution:
    """Resultado da resolução: ordem de tentativa e metadados para diagnóstico/erros."""

    attempt_chain: tuple[str, ...]
    reason: str
    available_engines: tuple[str, ...] = ()
    missing_engines: tuple[str, ...] = ()
    install_hints: tuple[str, ...] = ()


def _os_label() -> str:
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    if s == "linux":
        return "linux"
    return s or "unknown"


def _libreoffice_ok() -> bool:
    # O resolver participa do request HTTP: não inicie ``soffice --version``
    # apenas para montar a cadeia. A conversão real valida o executável e cai
    # para o próximo motor se a instalação estiver incompleta.
    return bool(resolve_libreoffice_binary(verify_version=False))



def _word_ok() -> bool:
    return is_word_pdf_available()


def _weasy_import_ok() -> bool:
    """
    No Windows (e noutros SO sem GTK/Pango), `import weasyprint` pode levantar
    `OSError` ao carregar `libgobject` — não só `ImportError`.
    """
    try:
        import weasyprint  # noqa: F401

        return True
    except (ImportError, OSError):
        return False


def _fpdf_ok() -> bool:
    try:
        import fpdf  # noqa: F401

        return True
    except ImportError:
        return False


def _simple_fallback_allowed() -> bool:
    if not _fpdf_ok():
        return False
    if getattr(settings, "DOCUMENTOS_SIMPLE_PDF_FALLBACK", False):
        return True
    if getattr(settings, "DOCUMENTOS_PDF_AUTO_FALLBACK", False) and getattr(settings, "DEBUG", False):
        return True
    return False


def _scan_availability_uncached(
    memo: dict[str, bool] | None = None,
) -> tuple[list[str], list[str]]:
    avail: list[str] = []
    missing: list[str] = []
    for name, probe in (
        ("word_com", _word_ok),
        ("libreoffice", _libreoffice_ok),
        ("weasyprint", _weasy_import_ok),
        ("simple_fallback", _simple_fallback_allowed),
    ):
        if memo is not None and name in _STABLE_PROBE_NAMES:
            if name not in memo:
                memo[name] = probe()
            ok = memo[name]
        else:
            ok = probe()
        if ok:
            avail.append(name)
        else:
            missing.append(name)
    return avail, missing


def _scan_availability() -> tuple[list[str], list[str]]:
    """Sonda motores no máximo uma vez por janela e por configuração.

    Importar motores opcionais pode carregar bibliotecas nativas. Repetir essas
    sondagens durante a mesma requisição consumia centenas de milissegundos até
    em cache hit.
    """
    ttl = max(
        0,
        int(getattr(settings, "DOCUMENTOS_ENGINE_PROBE_CACHE_SECONDS", 60) or 0),
    )
    if ttl == 0:
        return _scan_availability_uncached()

    bucket = int(time.monotonic() // ttl)
    config = (
        platform.system(),
        getattr(settings, "DOCUMENTOS_LIBREOFFICE_BINARY", None),
        getattr(settings, "DOCUMENTOS_SIMPLE_PDF_FALLBACK", False),
        getattr(settings, "DOCUMENTOS_PDF_AUTO_FALLBACK", False),
        getattr(settings, "DEBUG", False),
        # mock.patch troca a função; incluir a identidade mantém os testes
        # isolados e também permite substituições controladas em runtime.
        id(_word_ok),
        id(_libreoffice_ok),
        id(_weasy_import_ok),
        id(_simple_fallback_allowed),
    )
    key = (bucket, *config)
    with _availability_cache_lock:
        cached = _availability_cache.get(key)
        if cached is not None:
            return list(cached[0]), list(cached[1])
        # Sobrevive à troca de janela: a mesma configuração continua valendo,
        # só o `bucket` mudou. É o que evita reabrir o Word e reimportar o
        # WeasyPrint a cada minuto.
        memo = _stable_probe_cache.get(config)
        if memo is None:
            _stable_probe_cache.clear()
            memo = _stable_probe_cache.setdefault(config, {})

    result = _scan_availability_uncached(memo)
    with _availability_cache_lock:
        _availability_cache.clear()
        _availability_cache[key] = (list(result[0]), list(result[1]))
    return result


def _auto_chain(*, prefer_docx_pipeline: bool, available: set[str] | None = None) -> list[str]:
    osys = platform.system()
    if prefer_docx_pipeline:
        if osys == "Windows":
            raw = ["word_com", "libreoffice", "weasyprint", "simple_fallback"]
        elif sys_platform_is_linux():
            raw = ["libreoffice", "weasyprint", "simple_fallback"]
        elif sys_platform_is_darwin():
            raw = ["libreoffice", "weasyprint", "word_com", "simple_fallback"]
        else:
            raw = ["libreoffice", "weasyprint", "simple_fallback"]
    else:
        if osys == "Windows":
            raw = ["word_com", "libreoffice", "weasyprint", "simple_fallback"]
        elif sys_platform_is_linux():
            raw = ["libreoffice", "weasyprint", "simple_fallback"]
        elif sys_platform_is_darwin():
            raw = ["libreoffice", "weasyprint", "word_com", "simple_fallback"]
        else:
            raw = ["libreoffice", "weasyprint", "simple_fallback"]
    if available is None:
        available = set(_scan_availability()[0])
    return [e for e in raw if e in available]


def _engine_available(name: str) -> bool:
    if name == "word_com":
        return _word_ok()
    if name == "libreoffice":
        return _libreoffice_ok()
    if name == "weasyprint":
        return _weasy_import_ok()
    if name == "simple_fallback":
        return _simple_fallback_allowed()
    return False


def _explicit_chain(
    explicit: str,
    *,
    auto_fallback: bool,
    available: set[str] | None = None,
) -> list[str]:
    explicit = (explicit or "").strip().lower()
    if explicit == "simple":
        explicit = "simple_fallback"
    if explicit in ("", "auto"):
        return []
    if explicit not in ("word_com", "libreoffice", "weasyprint", "simple_fallback"):
        return []
    if available is None:
        available = set(_scan_availability()[0])
    out: list[str] = []
    if explicit in available:
        out.append(explicit)
    elif not auto_fallback:
        return []
    if auto_fallback:
        for e in ("libreoffice", "weasyprint", "word_com", "simple_fallback"):
            if e != explicit and e in available and e not in out:
                out.append(e)
    return out


def _module_present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False



def build_pdf_unavailable_message(resolution: PdfEngineResolution) -> str:
    osn = _os_label()
    hints = "\n".join(f"  - {h}" for h in resolution.install_hints) if resolution.install_hints else ""
    base = (
        "Não foi possível gerar PDF. Nenhum motor PDF disponível na ordem configurada.\n"
        f"Sistema: {osn}\n"
        f"Motores ausentes ou indisponíveis: {', '.join(resolution.missing_engines) or '(n/d)'}\n"
    )
    if hints:
        base += f"Opções:\n{hints}\n"
    base += "  - Diagnóstico: python manage.py documentos_check\n"
    return base.strip()


def _default_install_hints() -> list[str]:
    osn = _os_label()
    hints: list[str] = []
    if osn == "windows":
        hints.append("Instale Microsoft Word e: python -m pip install docx2pdf pywin32")
        hints.append("Ou instale LibreOffice: winget install TheDocumentFoundation.LibreOffice")
        hints.append("Ou defina DOCUMENTOS_DEFAULT_PDF_ENGINE=weasyprint se o GTK estiver configurado.")
    elif osn == "linux":
        hints.append("Instale LibreOffice: sudo apt update && sudo apt install -y libreoffice")
        hints.append("Ou configure DOCUMENTOS_LIBREOFFICE_BINARY=/usr/bin/libreoffice")
    elif osn == "macos":
        hints.append("Instale LibreOffice: brew install --cask libreoffice")
        hints.append(
            "Ou configure DOCUMENTOS_LIBREOFFICE_BINARY=/Applications/LibreOffice.app/Contents/MacOS/soffice"
        )
    return hints


def resolve_pdf_engine(
    *,
    explicit_setting: str | None,
    prefer_docx_pipeline: bool,
) -> PdfEngineResolution:
    """
    Devolve a lista ordenada de motores a tentar.

    `prefer_docx_pipeline` é verdadeiro quando existe `docxtpl_context` plano (ex.: ofício, justificativa).
    """
    explicit = (explicit_setting or "auto").strip().lower()
    auto_fb = bool(getattr(settings, "DOCUMENTOS_PDF_AUTO_FALLBACK", False))

    if explicit in {"simple", "simple_fallback"} and _module_present("fpdf"):
        return PdfEngineResolution(
            attempt_chain=("simple_fallback",),
            reason="motor explícito: simple",
            available_engines=("simple_fallback",),
            missing_engines=(),
            install_hints=tuple(_default_install_hints()),
        )

    avail, missing = _scan_availability()
    available = set(avail)

    if explicit == "auto":
        chain = _auto_chain(
            prefer_docx_pipeline=prefer_docx_pipeline,
            available=available,
        )
        reason = "auto: primeira opção disponível por SO e fidelidade ao DOCX"
    else:
        chain = _explicit_chain(
            explicit,
            auto_fallback=auto_fb,
            available=available,
        )
        reason = f"motor explícito: {explicit}" + (" + fallback" if auto_fb else "")

    hints = _default_install_hints()
    if not chain:
        return PdfEngineResolution(
            attempt_chain=(),
            reason=reason,
            available_engines=tuple(avail),
            missing_engines=tuple(missing),
            install_hints=tuple(hints),
        )

    return PdfEngineResolution(
        attempt_chain=tuple(chain),
        reason=reason,
        available_engines=tuple(avail),
        missing_engines=tuple(missing),
        install_hints=tuple(hints),
    )
