from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    name = 'auditoria'

    def ready(self):
        from .signals import conectar_signals_de_auditoria

        conectar_signals_de_auditoria()
