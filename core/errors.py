from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

_LOGGER = logging.getLogger("core.errors")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return str(value)


def _capture_remote(exc: BaseException, contexto: str, dados: Mapping[str, Any]) -> None:
    from django.conf import settings

    if not getattr(settings, "SENTRY_DSN", ""):
        return
    try:
        import sentry_sdk

        if not sentry_sdk.is_initialized():
            return
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("error.context", contexto)
            scope.set_context("error_data", _json_safe(dados))
            sentry_sdk.capture_exception(exc)
    except Exception:
        _LOGGER.warning("Falha ao encaminhar exceção para o backend externo", exc_info=True)


def capture(
    exc: BaseException,
    contexto: str,
    *,
    logger: logging.Logger | None = None,
    level: int = logging.ERROR,
    **dados: Any,
) -> BaseException:
    """Registra uma exceção com contexto estável e campos estruturados."""

    if not isinstance(exc, BaseException):
        raise TypeError("exc deve ser uma exceção")
    contexto = (contexto or "").strip()
    if not contexto:
        raise ValueError("contexto não pode ser vazio")

    target = logger or _LOGGER
    target.log(
        level,
        "Falha capturada em %s",
        contexto,
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={
            "error_context": contexto,
            "error_type": type(exc).__name__,
            "error_data": _json_safe(dados),
        },
    )
    _capture_remote(exc, contexto, dados)
    return exc
