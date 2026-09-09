"""
Medição de tempo por etapa da geração documental (logging apenas; sem impacto na UI).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any


logger = logging.getLogger("documentos.timing")


def track_document_generation(label: str):
    """Decora um ponto de entrada documental e mede sua duração no log."""

    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            with measure_step(label, track_sla=True):
                return func(*args, **kwargs)

        return wrapped

    return decorator


@contextmanager
def measure_step(
    label: str,
    metadata: dict[str, Any] | None = None,
    *,
    track_sla: bool = False,
) -> Iterator[None]:
    """
    Regista duração em milissegundos no logger ``documentos.timing``.

    Nunca propaga falhas de logging para não interferir na geração do documento.
    """
    meta = dict(metadata or {})
    t0 = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        try:
            parts: list[str] = ["[documentos]"]
            for key in sorted(meta.keys()):
                val = meta[key]
                if val is None or val == "":
                    continue
                parts.append(f"{key}={val}")
            parts.append(f"etapa={label}")
            parts.append(f"duration_ms={duration_ms}")
            logger.info(" ".join(parts))
        except Exception as exc:
            logger.exception("Falha ao registrar etapa documental %s", label)
