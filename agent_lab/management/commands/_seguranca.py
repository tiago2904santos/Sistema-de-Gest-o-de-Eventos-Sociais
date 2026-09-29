"""Travas comuns aos comandos que escrevem no banco (ver agent_lab/environment.py)."""

from django.core.management.base import CommandError

from agent_lab.environment import AmbienteRecusado, exigir


def exigir_banco_descartavel():
    """Só LAB (marca interna) ou banco novo com cara de laboratório."""
    try:
        info = exigir("reset", permitir_banco_novo_de_lab=True)
    except AmbienteRecusado as exc:
        raise CommandError(str(exc)) from exc
    return f"{info['database']['name']} [{info['environment']}]"
