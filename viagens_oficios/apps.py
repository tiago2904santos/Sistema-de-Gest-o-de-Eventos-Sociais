from django.apps import AppConfig

class ViagensOficiosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "viagens_oficios"

    def ready(self):
        from . import checks  # noqa: F401
        from .regeneracao import registrar_regeradores
        registrar_regeradores()
