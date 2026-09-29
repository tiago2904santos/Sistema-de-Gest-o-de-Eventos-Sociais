"""Relógio ancorado do laboratório (ver AgentLabConfig.ready).

Troca o *código* de ``django.utils.timezone.now`` mantendo o mesmo objeto
função. Isso importa: ``default=timezone.now`` nos modelos e nas migrações
aponta para esse objeto, e o autodetector de migrações compara identidade —
substituir o atributo do módulo faria ``makemigrations`` ver mudanças falsas.
"""

import datetime as _dt
import time

from django.utils import timezone

_ORIGINAL_CODE = timezone.now.__code__


def _now_ancorado():  # executa com os globals de django.utils.timezone
    alvo, inicio = _lab_anchor  # noqa: F821 — injetado no módulo timezone
    return (alvo + timedelta(seconds=_lab_monotonic() - inicio)).astimezone(timezone.utc)  # noqa: F821


def ancorar(iso: str):
    alvo = _dt.datetime.fromisoformat(iso)
    if alvo.tzinfo is None:
        alvo = timezone.make_aware(alvo)
    globais = timezone.now.__globals__
    globais["_lab_anchor"] = (alvo, time.monotonic())
    globais["_lab_monotonic"] = time.monotonic
    timezone.now.__code__ = _now_ancorado.__code__
    return timezone.now


def desancorar():
    timezone.now.__code__ = _ORIGINAL_CODE


def ancorado():
    return timezone.now.__code__ is not _ORIGINAL_CODE
