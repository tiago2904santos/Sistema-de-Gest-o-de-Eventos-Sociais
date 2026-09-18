from django.apps import AppConfig


class ViagensPlanosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "viagens_planos"
    verbose_name = "Viagens — planos de trabalho"

    def ready(self):
        from .regeneracao import registrar_regeradores
        registrar_regeradores()
