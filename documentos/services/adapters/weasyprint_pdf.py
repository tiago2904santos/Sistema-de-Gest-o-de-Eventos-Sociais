from __future__ import annotations

from pathlib import Path
from typing import Mapping

from django.conf import settings
from django.template.loader import render_to_string

from documentos.services.resources_paths import resolve_stylesheet_path


def render_pdf_bytes_weasyprint(
    *,
    html_template_name: str,
    context: Mapping[str, object],
    stylesheet_paths: tuple[str, ...],
) -> bytes:
    try:
        from weasyprint import CSS
        from weasyprint import HTML
    except OSError as exc:
        raise RuntimeError(
            "WeasyPrint não pôde carregar bibliotecas nativas (GTK/Pango/Cairo). "
            "Instale as dependências ou use DOCUMENTOS_DEFAULT_PDF_ENGINE=libreoffice."
        ) from exc

    html_string = render_to_string(html_template_name, dict(context))
    base_url = getattr(settings, "DOCUMENTOS_BASE_URL", None)
    if not base_url:
        base_url = Path(settings.BASE_DIR).resolve().as_uri() + "/"
    stylesheets = []
    for rel in stylesheet_paths:
        css_path = resolve_stylesheet_path(rel)
        if css_path.exists():
            stylesheets.append(CSS(filename=str(css_path)))
    # Não habilitar dicas de apresentação vindas do HTML. Além de os nossos
    # templates não dependerem disso, essa opção reduz a superfície de ataque
    # ao renderizar conteúdo preenchido por usuários.
    return HTML(string=html_string, base_url=base_url).write_pdf(
        stylesheets=stylesheets,
        presentational_hints=False,
    )
