from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse
from django.http import Http404
from django.http import HttpResponse
from django.utils.http import content_disposition_header


def private_file_response(file_field, *, as_attachment: bool = False):
    """Serve a FileField somente depois de a view autorizar o objeto pai."""
    if not file_field or not file_field.name:
        raise Http404("Arquivo não encontrado.")

    filename = Path(file_field.name).name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    disposition = content_disposition_header(as_attachment, filename)

    if getattr(settings, "PRIVATE_MEDIA_X_ACCEL_REDIRECT", False):
        internal_prefix = getattr(
            settings,
            "PRIVATE_MEDIA_INTERNAL_URL",
            "/_protected_media/",
        ).rstrip("/")
        relative_name = quote(file_field.name.lstrip("/\\"), safe="/")
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = f"{internal_prefix}/{relative_name}"
        if disposition:
            response["Content-Disposition"] = disposition
    else:
        try:
            response = FileResponse(
                file_field.open("rb"),
                as_attachment=as_attachment,
                filename=filename,
                content_type=content_type,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise Http404("Arquivo não encontrado.") from exc

    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
