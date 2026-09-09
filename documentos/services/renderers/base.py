from dataclasses import dataclass
from typing import Mapping

from ..types import DocumentoFormato
from ..types import DocumentoTipo


class DocumentRendererError(Exception):
    pass


class RendererUnavailableError(DocumentRendererError):
    pass


@dataclass(frozen=True)
class RenderRequest:
    tipo: DocumentoTipo
    formato: DocumentoFormato
    payload: Mapping[str, object]
    template_content: str = ""
    reference: str | None = None


@dataclass(frozen=True)
class RenderResult:
    content: bytes
    content_type: str


class BaseDocumentRenderer:
    formato: DocumentoFormato

    def is_available(self) -> bool:
        return False

    def render(self, request: RenderRequest) -> RenderResult:
        raise RendererUnavailableError(f"Renderer indisponível para formato {request.formato.value}.")
