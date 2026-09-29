import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from agent_lab.audit_static import executar


class Command(BaseCommand):
    help = "Auditoria estática (CSS, templates, código, rotas) → reports/audit/static-findings.{json,md}."

    def handle(self, *args, **opts):
        destino = Path(settings.BASE_DIR) / "reports" / "audit"
        self.stdout.write(json.dumps(executar(destino), indent=2, ensure_ascii=False))
