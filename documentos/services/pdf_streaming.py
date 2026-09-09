"""Streaming de PDF inline com suporte a Range (200 / 206 / 416)."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from django.http import FileResponse
from django.http import HttpRequest
from django.http import HttpResponse

_RANGE_UNIT_RE = re.compile(r"^\s*bytes\s*=\s*(.+)\s*$", re.IGNORECASE)


class PdfStreamBackend(StrEnum):
    """Backend de armazenamento; apenas `local` está implementado."""

    LOCAL = "local"
    S3 = "s3"
    DB = "db"


def _content_disposition_inline(filename: str) -> str:
    encoded = quote(filename, safe="")
    return f"inline; filename*=UTF-8''{encoded}"


def apply_pdf_response_headers(response: HttpResponse, *, filename: str) -> None:
    response["Content-Type"] = "application/pdf"
    response["Content-Disposition"] = _content_disposition_inline(filename)
    response["Accept-Ranges"] = "bytes"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "SAMEORIGIN"
    response["Cross-Origin-Resource-Policy"] = "same-origin"
    # Documento oficial nao pode vir do cache do navegador: "Visualizar" aponta
    # sempre para a mesma URL por documento, entao sem isto uma retificacao
    # continuaria exibindo a versao anterior. O servidor ja regenera por hash do
    # conteudo; o que faltava era avisar o navegador.
    response["Cache-Control"] = "no-store, must-revalidate"
    response["Pragma"] = "no-cache"


def _parse_first_byte_range(range_header: str | None, file_size: int) -> tuple[int, int] | str | None:
    """
    Devolve (start, end) inclusive para o primeiro intervalo, None se ignorar Range (resposta 200),
    ou a string 'unsatisfiable' para 416.
    """
    if file_size == 0:
        return None
    if not range_header:
        return None
    m = _RANGE_UNIT_RE.match(range_header)
    if not m:
        return None
    spec = m.group(1).strip()
    if not spec or "," in spec:
        return None
    part = spec.split(",", 1)[0].strip()
    if "-" not in part:
        return None
    start_s, end_s = part.split("-", 1)
    try:
        if start_s == "" and end_s != "":
            suffix_len = int(end_s)
            if suffix_len <= 0:
                return None
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        elif start_s != "" and end_s == "":
            start = int(start_s)
            end = file_size - 1
        elif start_s != "" and end_s != "":
            start = int(start_s)
            end = int(end_s)
        else:
            return None
    except ValueError:
        return None

    if start < 0 or end < 0 or start > end:
        return "unsatisfiable"
    if start >= file_size:
        return "unsatisfiable"
    end = min(end, file_size - 1)
    if start > end:
        return "unsatisfiable"
    return start, end


def build_pdf_inline_response(
    request: HttpRequest,
    *,
    file_path: str | Path,
    filename: str,
    backend: PdfStreamBackend = PdfStreamBackend.LOCAL,
) -> HttpResponse:
    """
    Constrói HttpResponse para servir um PDF com Content-Disposition inline e Range.

    `backend` reserva extensão para S3/DB; apenas `local` é suportado.
    """
    if backend is not PdfStreamBackend.LOCAL:
        raise NotImplementedError(f"Backend de PDF não implementado: {backend}")

    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))

    file_size = path.stat().st_size
    parsed = _parse_first_byte_range(request.META.get("HTTP_RANGE"), file_size)

    if parsed == "unsatisfiable":
        resp = HttpResponse(status=416)
        resp["Content-Range"] = f"bytes */{file_size}"
        resp["Content-Type"] = "application/pdf"
        return resp

    if parsed is None:
        handle: BinaryIO = path.open("rb")
        response = FileResponse(handle, as_attachment=False, filename=filename)
        apply_pdf_response_headers(response, filename=filename)
        if file_size:
            response["Content-Length"] = str(file_size)
        return response

    start, end = parsed
    length = end - start + 1
    with path.open("rb") as f:
        f.seek(start)
        chunk = f.read(length)

    response = HttpResponse(chunk, status=206, content_type="application/pdf")
    apply_pdf_response_headers(response, filename=filename)
    response["Content-Length"] = str(len(chunk))
    response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return response


def build_pdf_inline_from_file_object(
    request: HttpRequest,
    *,
    file_obj: BinaryIO,
    file_size: int,
    filename: str,
    backend: PdfStreamBackend = PdfStreamBackend.LOCAL,
) -> HttpResponse:
    """
    Variante para ficheiros já abertos (ex.: testes ou storage que não expõe path local).
    """
    if backend is not PdfStreamBackend.LOCAL:
        raise NotImplementedError(f"Backend de PDF não implementado: {backend}")

    parsed = _parse_first_byte_range(request.META.get("HTTP_RANGE"), file_size)

    if parsed == "unsatisfiable":
        resp = HttpResponse(status=416)
        resp["Content-Range"] = f"bytes */{file_size}"
        resp["Content-Type"] = "application/pdf"
        return resp

    if parsed is None:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        response = FileResponse(file_obj, as_attachment=False, filename=filename)
        apply_pdf_response_headers(response, filename=filename)
        if file_size:
            response["Content-Length"] = str(file_size)
        return response

    start, end = parsed
    length = end - start + 1
    if hasattr(file_obj, "seek"):
        file_obj.seek(start)
    chunk = file_obj.read(length)

    response = HttpResponse(chunk, status=206, content_type="application/pdf")
    apply_pdf_response_headers(response, filename=filename)
    response["Content-Length"] = str(len(chunk))
    response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return response
