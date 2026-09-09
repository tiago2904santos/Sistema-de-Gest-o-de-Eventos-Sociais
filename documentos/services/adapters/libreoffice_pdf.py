from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

# Invocações concorrentes de `soffice` sem perfil isolado disputam o lock do
# perfil de utilizador padrão (~/.config/libreoffice/.../.lock): uma delas
# falha ou bloqueia indefinidamente. `-env:UserInstallation` isola cada
# chamada no seu próprio diretório temporário, eliminando essa disputa.
_LIBREOFFICE_TIMEOUT_SECONDS = 90


def _conversion_cache_key(*, data: bytes, source_format: str, engine: str) -> str:
    version = str(getattr(settings, "DOCUMENTOS_GENERATOR_VERSION", "1") or "1")
    digest = hashlib.sha256(data).hexdigest()
    return f"cv3:document-conversion:{version}:{engine}:{source_format}:{digest}"


def _convert_with_cache(*, data: bytes, source_format: str, engine: str, converter) -> bytes:
    enabled = bool(getattr(settings, "DOCUMENTOS_BINARY_CONVERSION_CACHE", True))
    key = _conversion_cache_key(data=data, source_format=source_format, engine=engine)
    if enabled:
        cached = cache.get(key)
        if isinstance(cached, bytes) and cached.startswith(b"%PDF"):
            return cached

    result = converter()
    if enabled:
        timeout = int(getattr(settings, "DOCUMENTOS_BINARY_CACHE_SECONDS", 86400) or 86400)
        cache.set(key, result, timeout=max(1, timeout))
    return result


def _headless_subprocess_kwargs() -> dict[str, int]:
    if os.name != "nt":
        return {}
    return {"creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0))}


def _convert_via_libreoffice(*, input_bytes: bytes, filename: str, libreoffice_binary: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        input_path = tdir / filename
        input_path.write_bytes(input_bytes)
        profile_dir = tdir / "profile"
        profile_dir.mkdir()
        try:
            subprocess.run(
                [
                    libreoffice_binary,
                    f"-env:UserInstallation={profile_dir.as_uri()}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tdir),
                    str(input_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=_LIBREOFFICE_TIMEOUT_SECONDS,
                **_headless_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"LibreOffice não respondeu em {_LIBREOFFICE_TIMEOUT_SECONDS}s (possível disputa de conversões concorrentes)."
            ) from exc
        pdf_path = tdir / f"{input_path.stem}.pdf"
        if not pdf_path.exists():
            raise RuntimeError("LibreOffice não gerou o arquivo PDF esperado.")
        return pdf_path.read_bytes()


def convert_docx_to_pdf_libreoffice(*, docx_bytes: bytes, libreoffice_binary: str) -> bytes:
    """
    Converte DOCX em PDF via LibreOffice em modo headless (sem unoserver).
    """
    return _convert_with_cache(
        data=docx_bytes,
        source_format="docx",
        engine="libreoffice",
        converter=lambda: _convert_via_libreoffice(
            input_bytes=docx_bytes,
            filename="entrada.docx",
            libreoffice_binary=libreoffice_binary,
        ),
    )



def convert_xlsx_to_pdf_libreoffice(*, xlsx_bytes: bytes, libreoffice_binary: str) -> bytes:
    """Converte XLSX em PDF via LibreOffice em modo headless (sem unoserver)."""
    return _convert_with_cache(
        data=xlsx_bytes,
        source_format="xlsx",
        engine="libreoffice",
        converter=lambda: _convert_via_libreoffice(
            input_bytes=xlsx_bytes,
            filename="entrada.xlsx",
            libreoffice_binary=libreoffice_binary,
        ),
    )
