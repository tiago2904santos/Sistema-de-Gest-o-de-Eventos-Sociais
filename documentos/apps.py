from django.apps import AppConfig


class DocumentosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documentos"
    verbose_name = "Documentos"

    def ready(self):
        from accounts.modulos import registrar_namespace

        registrar_namespace("documentos", "VIAGENS")
