import json

from django.core.management.base import BaseCommand, CommandError

from agent_lab.api_intel import executar
from agent_lab.environment import AmbienteRecusado, exigir


class Command(BaseCommand):
    help = "Descobre endpoints JSON, infere schema, gera OpenAPI e confere contrato (docs/api/)."

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true", help="regrava docs/api/contracts.json")
        parser.add_argument("--check", action="store_true", help="falha se houver quebra de contrato")

    def handle(self, *args, **o):
        try:
            exigir("write")  # usa o cliente de teste com login; só em LAB/DEV
        except AmbienteRecusado as exc:
            raise CommandError(str(exc)) from exc
        r = executar(atualizar=o["update"], checar=o["check"])
        self.stdout.write(json.dumps(r, ensure_ascii=False, indent=2))
        if o["check"] and r.get("breaking"):
            raise CommandError(f"{len(r['breaking'])} quebra(s) de contrato")
