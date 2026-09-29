"""Travas comuns aos comandos que escrevem no banco."""

import os

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection

MARCADORES_SEGUROS = ("dev", "lab", "test", "ci", "local", "sandbox", "tmp")


def exigir_banco_descartavel():
    if not settings.DEBUG:
        raise CommandError("Recusado: DEBUG desligado. Estes comandos só rodam em desenvolvimento.")
    nome = str(connection.settings_dict.get("NAME", ""))
    if connection.vendor == "sqlite":
        return nome
    if os.environ.get("AGENT_LAB_ALLOW_RESET") == "1":
        return nome
    if not any(m in nome.lower() for m in MARCADORES_SEGUROS):
        raise CommandError(
            f"Recusado: o banco '{nome}' não parece descartável (o nome precisa conter um de "
            f"{MARCADORES_SEGUROS}). Se tiver certeza, exporte AGENT_LAB_ALLOW_RESET=1."
        )
    return nome
