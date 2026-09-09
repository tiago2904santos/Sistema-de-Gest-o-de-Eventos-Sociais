from django.apps import AppConfig

class ViagensPrestacoesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "viagens_prestacoes"
    verbose_name = "Viagens — Prestações de contas"

    def ready(self):
        from accounts.modulos import registrar_namespace
        registrar_namespace("viagens_prestacoes", "VIAGENS")
        from .signals import connect_signals
        connect_signals()
