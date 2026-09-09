"""
Resolve o executável do LibreOffice para conversão DOCX→PDF (útil no Windows sem GTK do WeasyPrint).

Ordem de precedência:
1. Variáveis de ambiente: DOCUMENTOS_LIBREOFFICE_BINARY, SOFFICE_PATH, LIBREOFFICE_SOFFICE
2. Django settings.DOCUMENTOS_LIBREOFFICE_BINARY
3. PATH: soffice, libreoffice, lowriter
4. Caminhos típicos por sistema operativo (Windows, Linux, macOS)
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from pathlib import Path

import sys

from django.conf import settings


def sys_platform_is_linux() -> bool:
    return sys.platform.startswith("linux")


def sys_platform_is_darwin() -> bool:
    return sys.platform == "darwin"


def _readable_file(path: str | Path) -> bool:
    return Path(path).is_file()


def _prefer_windows_console_binary(binary: str) -> str:
    """Prefer ``soffice.com`` so headless failures never open a GUI dialog."""
    path = Path(binary)
    if os.name == "nt" and path.name.lower() == "soffice.exe":
        console_binary = path.with_suffix(".com")
        if console_binary.is_file():
            return str(console_binary)
    return binary


def verify_libreoffice_binary(binary: str, *, timeout_seconds: float = 5.0) -> bool:
    """Executa `binary --version` com timeout curto; útil para diagnóstico."""
    original_binary = binary
    binary = _prefer_windows_console_binary(binary)
    if os.name == "nt" and Path(original_binary).suffix.lower() == ".exe" and binary == original_binary:
        # O executável gráfico pode exibir MessageBox antes de processar
        # ``--headless``. Sem o irmão de console não há uma sondagem silenciosa.
        return False
    run_kwargs: dict[str, object] = {}
    if os.name == "nt":
        run_kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        r = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            **run_kwargs,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _iter_candidates() -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    def add(p: str) -> None:
        p = (p or "").strip()
        if not p or p in seen:
            return
        p = _prefer_windows_console_binary(p)
        seen.add(p)
        ordered.append(p)

    for key in ("DOCUMENTOS_LIBREOFFICE_BINARY", "SOFFICE_PATH", "LIBREOFFICE_SOFFICE"):
        add(os.getenv(key) or "")

    explicit = (getattr(settings, "DOCUMENTOS_LIBREOFFICE_BINARY", None) or "").strip()
    add(explicit)

    for name in ("soffice", "libreoffice", "lowriter"):
        found = shutil.which(name)
        if found:
            add(found)

    if os.name == "nt":
        for candidate in (
            Path(r"C:\Program Files\LibreOffice\program\soffice.com"),
            Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
            Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.com"),
            Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
        ):
            add(str(candidate))
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            programs = Path(local) / "Programs"
            if programs.is_dir():
                for child in sorted(programs.glob("LibreOffice*")):
                    add(str(child / "program" / "soffice.com"))
                    add(str(child / "program" / "soffice.exe"))

    if sys_platform_is_linux():
        for candidate in (
            Path("/usr/bin/libreoffice"),
            Path("/usr/bin/soffice"),
            Path("/snap/bin/libreoffice"),
            Path("/usr/local/bin/libreoffice"),
            Path("/usr/local/bin/soffice"),
        ):
            add(str(candidate))
        for match in sorted(glob.glob("/opt/libreoffice*/program/soffice")):
            add(match)

    if sys_platform_is_darwin():
        for candidate in (
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
            Path("/Applications/LibreOffice.app/Contents/MacOS/libreoffice"),
        ):
            add(str(candidate))
        for prefix in (Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
            for name in ("soffice", "libreoffice"):
                add(str(prefix / name))

    if not sys_platform_is_linux() and not sys_platform_is_darwin() and os.name != "nt":
        for candidate in (Path("/usr/bin/libreoffice"), Path("/usr/bin/soffice")):
            add(str(candidate))

    return ordered


def resolve_libreoffice_binary(*, verify_version: bool = False) -> str | None:
    """
    Devolve o primeiro caminho de executável LibreOffice/soffice encontrado, ou None.

    Se verify_version=True, só aceita binários que respondem a `--version` no timeout.
    """
    for candidate in _iter_candidates():
        if not _readable_file(candidate):
            continue
        if verify_version and not verify_libreoffice_binary(candidate):
            continue
        return candidate
    return None
