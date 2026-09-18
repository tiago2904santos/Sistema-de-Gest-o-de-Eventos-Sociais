from django.apps import AppConfig


class ViagensOrdensConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "viagens_ordens"
    verbose_name = "Viagens — ordens de serviço"

    def ready(self):
        from .regeneracao import registrar_regeradores
        registrar_regeradores()
