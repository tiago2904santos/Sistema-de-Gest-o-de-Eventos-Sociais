"""Semeia um cenário determinístico (aditivo; a base é idempotente)."""

import json

from django.core.management.base import BaseCommand, CommandError

from agent_lab.seed import CENARIOS, Semeador, carregar_cenario

from ._seguranca import exigir_banco_descartavel


class Command(BaseCommand):
    help = "Semeia dados determinísticos: " + ", ".join(CENARIOS)

    def add_arguments(self, parser):
        parser.add_argument(
            "--scenario", default="normal", help="embutido (" + ", ".join(CENARIOS) + ") ou tests/scenarios/<nome>.json"
        )

    def handle(self, *args, **opts):
        banco = exigir_banco_descartavel()
        self.stdout.write(f"Semeando cenário '{opts['scenario']}' em {banco}…")
        nome = opts["scenario"]
        custom = None if nome in CENARIOS else carregar_cenario(nome)
        if nome not in CENARIOS and custom is None:
            raise CommandError(f"Cenário desconhecido: {nome}")
        relatorio, erros = Semeador(nome, stdout=self.stdout, custom=custom).executar()
        self.stdout.write(json.dumps({"counts": relatorio, "errors": erros}, ensure_ascii=False, indent=2))
        if erros:
            raise CommandError(f"{len(erros)} etapa(s) do seed falharam: {', '.join(erros)}")
        self.stdout.write(self.style.SUCCESS("Seed concluído."))
