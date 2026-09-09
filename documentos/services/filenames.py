import re
import unicodedata
from datetime import datetime

from django.utils import timezone

from .types import DocumentoFormato
from .types import DocumentoTipo


_NON_WORD_RE = re.compile(r"[^a-z0-9_-]+")


def slugify_filename_part(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.strip().lower().replace(" ", "_")
    normalized = _NON_WORD_RE.sub("_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "documento"


def build_document_filename(
    tipo: DocumentoTipo,
    formato: DocumentoFormato,
    *,
    reference: str | None = None,
    now: datetime | None = None,
) -> str:
    ref_part = slugify_filename_part(reference) if reference else "sem_referencia"
    current = now or timezone.now()
    if timezone.is_aware(current):
        current = timezone.localtime(current)
    dt = current.strftime("%Y%m%d-%H%M%S")
    return f"{tipo.value}_{ref_part}_{dt}.{formato.value}"
