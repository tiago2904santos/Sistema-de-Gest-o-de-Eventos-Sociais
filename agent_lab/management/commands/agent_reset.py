"""Volta o banco de desenvolvimento a um estado previsível: esquema do zero + seed."""

from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

from agent_lab.seed import CENARIOS

from ._seguranca import exigir_banco_descartavel


class Command(BaseCommand):
    help = "Apaga o banco de DESENVOLVIMENTO, reaplica as migrações e semeia um cenário."

    def add_arguments(self, parser):
        parser.add_argument("--scenario", default="normal", choices=sorted(CENARIOS))
        parser.add_argument("--sem-seed", action="store_true")

    def handle(self, *args, **opts):
        banco = exigir_banco_descartavel()
        self.stdout.write(f"Recriando o esquema de {banco}…")
        if connection.vendor == "postgresql":
            with connection.cursor() as c:
                c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        elif connection.vendor == "sqlite":
            connection.close()
            Path(banco).unlink(missing_ok=True)
        else:
            call_command("flush", interactive=False, verbosity=0)
        call_command("migrate", interactive=False, verbosity=0)
        call_command("createcachetable", verbosity=0)
        if not opts["sem_seed"]:
            call_command("agent_seed", scenario=opts["scenario"], stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(f"Ambiente resetado no cenário '{opts['scenario']}'."))
