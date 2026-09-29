"""Relógio ancorado do laboratório (ver AgentLabConfig.ready)."""

import datetime as _dt
import time

from django.utils import timezone

_original_now = timezone.now


def ancorar(iso: str):
    alvo = _dt.datetime.fromisoformat(iso)
    if alvo.tzinfo is None:
        alvo = timezone.make_aware(alvo)
    inicio_real = time.monotonic()

    def agora():
        return (alvo + _dt.timedelta(seconds=time.monotonic() - inicio_real)).astimezone(_dt.timezone.utc)

    timezone.now = agora
    # localdate()/localtime() chamam timezone.now() internamente — seguem a âncora.
    return agora
