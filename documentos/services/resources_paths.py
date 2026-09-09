from __future__ import annotations

from pathlib import Path

from django.conf import settings


def get_documentos_resources_dir() -> Path:
    return Path(getattr(settings, "DOCUMENTOS_RESOURCES_DIR", settings.BASE_DIR / "documentos" / "resources"))


def resolve_resource_docx(relative_path: str) -> Path:
    base = get_documentos_resources_dir()
    path = (base / relative_path).resolve()
    try:
        base_resolved = base.resolve()
        path.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError("Caminho de template DOCX fora do diretório de recursos.") from exc
    return path


def resolve_stylesheet_path(path_str: str) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p
    return (Path(settings.BASE_DIR) / path_str).resolve()
