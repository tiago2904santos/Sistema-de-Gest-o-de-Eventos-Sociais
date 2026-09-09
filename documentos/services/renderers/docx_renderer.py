from typing import Callable

from ..types import DocumentoFormato
from .base import BaseDocumentRenderer
from .base import RenderRequest
from .base import RenderResult
from .base import RendererUnavailableError


class DocxRenderer(BaseDocumentRenderer):
    formato = DocumentoFormato.DOCX

    def __init__(self, adapter: Callable[[RenderRequest], bytes] | None = None):
        self._adapter = adapter

    def is_available(self) -> bool:
        return self._adapter is not None

    def render(self, request: RenderRequest) -> RenderResult:
        if request.formato != self.formato:
            raise RendererUnavailableError("Renderer DOCX recebeu formato incompatível.")
        if not self._adapter:
            raise RendererUnavailableError("Renderer DOCX sem adapter configurado.")
        content = self._adapter(request)
        return RenderResult(
            content=content,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
