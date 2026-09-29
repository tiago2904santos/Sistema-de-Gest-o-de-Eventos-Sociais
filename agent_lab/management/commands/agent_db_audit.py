import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from agent_lab.db_audit import executar


class Command(BaseCommand):
    help = "Auditoria do banco (estrutura; com --dados, também contagens e duplicidades) → reports/data/."

    def add_arguments(self, parser):
        parser.add_argument("--dados", action="store_true")

    def handle(self, *args, **opts):
        r = executar(Path(settings.BASE_DIR) / "reports" / "data", com_dados=opts["dados"])
        self.stdout.write(json.dumps(r, indent=2))
