"""Semeia um cenário determinístico (aditivo; a base é idempotente)."""

import json

from django.core.management.base import BaseCommand, CommandError

from agent_lab.seed import CENARIOS, Semeador

from ._seguranca import exigir_banco_descartavel


class Command(BaseCommand):
    help = "Semeia dados determinísticos: " + ", ".join(CENARIOS)

    def add_arguments(self, parser):
        parser.add_argument("--scenario", default="normal", choices=sorted(CENARIOS))

    def handle(self, *args, **opts):
        banco = exigir_banco_descartavel()
        self.stdout.write(f"Semeando cenário '{opts['scenario']}' em {banco}…")
        relatorio, erros = Semeador(opts["scenario"], stdout=self.stdout).executar()
        self.stdout.write(json.dumps({"counts": relatorio, "errors": erros}, ensure_ascii=False, indent=2))
        if erros:
            raise CommandError(f"{len(erros)} etapa(s) do seed falharam: {', '.join(erros)}")
        self.stdout.write(self.style.SUCCESS("Seed concluído."))
