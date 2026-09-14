from django.apps import AppConfig


class MigracaoLegadoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "migracao_legado"
    verbose_name = "Migração do Gerenciador de Viagens"
