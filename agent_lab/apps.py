import os

from django.apps import AppConfig


class AgentLabConfig(AppConfig):
    """Laboratório do agente: inventário, seed determinístico, UI Lab e auditoria.

    Só é instalado quando ``AGENT_LAB`` está ligado (padrão: ligado com DEBUG,
    desligado em produção). Nada de produção importa este app.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "agent_lab"
    verbose_name = "Laboratório do agente"

    def ready(self):
        # Relógio ancorado: com AGENT_LAB_FREEZE=2026-09-15T10:00:00-03:00 o
        # servidor "acorda" nessa data e o tempo corre a partir dela. Telas que
        # dizem "hoje", "há 3 dias" ou calculam prazos ficam estáveis para os
        # testes visuais, sem congelar o relógio (tokens e expirações seguem
        # funcionando).
        congelar = os.environ.get("AGENT_LAB_FREEZE")
        if congelar:
            from .clock import ancorar

            ancorar(congelar)
