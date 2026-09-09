import io
from datetime import datetime

from django.http import HttpRequest
from django.http import HttpResponse

from documentos.services.timing import measure_step

from .exceptions import UnsupportedDocumentFormat
from .filenames import build_document_filename
from .pdf_streaming import build_pdf_inline_from_file_object
from .types import DocumentoFormato
from .types import DocumentoTipo


def get_content_type_for_format(formato: DocumentoFormato) -> str:
    if formato == DocumentoFormato.DOCX:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if formato == DocumentoFormato.XLSX:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if formato == DocumentoFormato.PDF:
        return "application/pdf"
    value = getattr(formato, "value", str(formato))
    raise UnsupportedDocumentFormat(f"Formato não suportado: {value}")


def build_download_response(
    *,
    content: bytes,
    tipo: DocumentoTipo,
    formato: DocumentoFormato,
    reference: str | None = None,
    now: datetime | None = None,
    cache_hit: bool | None = None,
) -> HttpResponse:
    with measure_step(
        "build_download_response",
        {"tipo": tipo.value, "formato": formato.value, "reference": reference or ""},
    ):
        filename = build_document_filename(tipo, formato, reference=reference, now=now)
        response = HttpResponse(content, content_type=get_content_type_for_format(formato))
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        # Documento oficial nao pode vir do cache do navegador: "Visualizar" aponta
        # sempre para a mesma URL por documento, entao sem isto uma retificacao
        # continuaria exibindo a versao anterior. O servidor ja regenera por hash do
        # conteudo; o que faltava era avisar o navegador.
        response["Cache-Control"] = "no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        if cache_hit is True:
            response["X-Document-Cache"] = "HIT"
        elif cache_hit is False:
            response["X-Document-Cache"] = "MISS"
        return response


def build_inline_pdf_response(
    request: HttpRequest,
    *,
    content: bytes,
    tipo: DocumentoTipo,
    reference: str | None = None,
    now: datetime | None = None,
    cache_hit: bool | None = None,
    x_document_sha256: str | None = None,
) -> HttpResponse:
    """
    PDF com Content-Disposition inline para iframe / viewer nativo; suporta Range via `pdf_streaming`.
    """
    filename = build_document_filename(tipo, DocumentoFormato.PDF, reference=reference, now=now)
    response = build_pdf_inline_from_file_object(
        request,
        file_obj=io.BytesIO(content),
        file_size=len(content),
        filename=filename,
    )
    if cache_hit is True:
        response["X-Document-Cache"] = "HIT"
    elif cache_hit is False:
        response["X-Document-Cache"] = "MISS"
    if x_document_sha256:
        response["X-Document-SHA256"] = x_document_sha256
    return response


def build_inline_pdf_response_from_download_response(
    request: HttpRequest,
    download_response: HttpResponse,
    *,
    tipo: DocumentoTipo,
    reference: str | None = None,
    now: datetime | None = None,
) -> HttpResponse:
    """Converte a resposta de `build_download_response` (bytes em memória) em PDF inline."""
    cache_hit: bool | None = None
    if "X-Document-Cache" in download_response:
        marker = download_response["X-Document-Cache"]
        if marker == "HIT":
            cache_hit = True
        elif marker == "MISS":
            cache_hit = False
    sha = download_response.get("X-Document-SHA256")
    return build_inline_pdf_response(
        request,
        content=download_response.content,
        tipo=tipo,
        reference=reference,
        now=now,
        cache_hit=cache_hit,
        x_document_sha256=sha,
    )
