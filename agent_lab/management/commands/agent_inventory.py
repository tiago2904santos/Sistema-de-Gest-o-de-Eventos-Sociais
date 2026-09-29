"""Gera o inventário do produto em ``ui-inventory/``."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from agent_lab.inventory import gerar


class Command(BaseCommand):
    help = "Gera ui-inventory/*.json (rotas, páginas, componentes, formulários, entidades, tokens...)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(Path(settings.BASE_DIR) / "ui-inventory"))
        parser.add_argument("--com-contagem", action="store_true", help="Inclui a contagem de linhas de cada tabela (depende do banco; não versionar).")

    def handle(self, *args, **opts):
        resumo = gerar(Path(opts["out"]), com_contagem=opts["com_contagem"])
        self.stdout.write(json.dumps(resumo, ensure_ascii=False, indent=2))
        self.stdout.write(self.style.SUCCESS(f"Inventário gravado em {opts['out']}"))
