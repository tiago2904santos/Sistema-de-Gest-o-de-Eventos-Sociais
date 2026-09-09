from __future__ import annotations

from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Mapping

from documentos.services.formatters import format_document_datetime


def _finalize(value):
    return format_document_datetime(value) if isinstance(value, datetime) else value


def render_docx_bytes(*, template_path: Path, context: Mapping[str, object]) -> bytes:
    try:
        from docxtpl import DocxTemplate
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Pacote 'docxtpl' não instalado no ambiente ativo. "
            "Execute: python -m pip install docxtpl python-docx"
        ) from exc

    tpl = DocxTemplate(str(template_path))
    from jinja2 import Environment

    tpl.render(dict(context), jinja_env=Environment(finalize=_finalize))
    buf = BytesIO()
    tpl.save(buf)
    return buf.getvalue()
