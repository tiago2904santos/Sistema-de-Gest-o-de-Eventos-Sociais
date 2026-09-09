from ..exceptions import DocumentRendererUnavailable
from ..exceptions import DocumentTemplateNotFound
from ..exceptions import UnsupportedDocumentType
from ..exceptions import UnsupportedDocumentFormat
from ..filenames import build_document_filename
from ..placeholders import ensure_no_unresolved_placeholders
from ..placeholders import ensure_required_placeholders
from ..placeholders import render_template_content
from ..registry import default_document_registry
from ..templates import default_template_registry
from .base import BaseDocumentRenderer
from .base import DocumentRendererError
from .base import RenderRequest
from .base import RenderResult
from .base import RendererUnavailableError
from .docx_renderer import DocxRenderer
from .pdf_renderer import PdfRenderer

DocumentRenderRequest = RenderRequest
DocumentRenderResult = RenderResult
DocumentRenderer = BaseDocumentRenderer


def _enum_value(value: object) -> str:
    return getattr(value, "value", str(value))


class NoopDocumentRenderer(BaseDocumentRenderer):
    def is_available(self) -> bool:
        return False

    def render(self, request: RenderRequest) -> RenderResult:
        _ = request
        raise DocumentRendererUnavailable("Nenhum renderer configurado para esta fase.")


def render_document(
    request: DocumentRenderRequest,
    *,
    renderer: DocumentRenderer | None = None,
    template_content: str = "",
    reference: str | None = None,
) -> tuple[DocumentRenderResult, str]:
    if not default_document_registry.has(request.tipo):
        raise UnsupportedDocumentType(f"Tipo documental não suportado: {_enum_value(request.tipo)}")

    type_definition = default_document_registry.get(request.tipo)
    if not type_definition.supports_format(request.formato):
        raise UnsupportedDocumentFormat(
            f"Formato {_enum_value(request.formato)} não suportado para {_enum_value(request.tipo)}",
        )

    if not default_template_registry.has(request.tipo, request.formato):
        raise DocumentTemplateNotFound(
            "Template não encontrado para tipo="
            f"{_enum_value(request.tipo)} e formato={_enum_value(request.formato)}",
        )

    template_definition = default_template_registry.get(request.tipo, request.formato)
    ensure_required_placeholders(request.payload, template_definition.required_placeholders)
    content_source = template_content or request.template_content or ""
    resolved_content = render_template_content(content_source, request.payload)
    ensure_no_unresolved_placeholders(resolved_content)

    selected_renderer = renderer or NoopDocumentRenderer()
    if not selected_renderer.is_available():
        raise DocumentRendererUnavailable(
            f"Renderer indisponível para formato {_enum_value(request.formato)}",
        )
    if request.formato != selected_renderer.formato:
        raise UnsupportedDocumentFormat(
            f"Renderer incompatível com formato {_enum_value(request.formato)}",
        )

    result = selected_renderer.render(request)
    filename = build_document_filename(
        request.tipo,
        request.formato,
        reference=reference or request.reference,
    )
    return result, filename


__all__ = [
    "BaseDocumentRenderer",
    "DocumentRenderRequest",
    "DocumentRenderResult",
    "DocumentRenderer",
    "DocumentRendererUnavailable",
    "DocumentRendererError",
    "DocxRenderer",
    "NoopDocumentRenderer",
    "PdfRenderer",
    "RenderRequest",
    "RenderResult",
    "RendererUnavailableError",
    "render_document",
]
