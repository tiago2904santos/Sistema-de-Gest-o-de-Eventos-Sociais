import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from agent_lab.depgraph import gerar


class Command(BaseCommand):
    help = "Gera o mapa de dependências em reports/architecture/."

    def handle(self, *args, **opts):
        destino = Path(settings.BASE_DIR) / "reports" / "architecture"
        self.stdout.write(json.dumps(gerar(destino), indent=2))
        self.stdout.write(self.style.SUCCESS(f"Mapa gravado em {destino}"))
