import json

from django.core.management.base import BaseCommand

from agent_lab.environment import detectar


class Command(BaseCommand):
    help = "Classifica o ambiente (LAB/DEV/STAGING/PRODUCTION) e mostra os sinais usados."

    def handle(self, *args, **opts):
        self.stdout.write(json.dumps(detectar(), ensure_ascii=False, indent=2))
