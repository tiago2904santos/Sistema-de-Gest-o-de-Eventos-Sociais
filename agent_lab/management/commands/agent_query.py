"""Consulta estruturada (JSON) sobre o projeto. Usada pelo project-mcp.

manage.py agent_query route /viagens/oficios/
manage.py agent_query model viagens_oficios.Oficio
manage.py agent_query known_problems P1
"""

import json

from django.core.management.base import BaseCommand, CommandError

from agent_lab.query import CONSULTAS


class Command(BaseCommand):
    help = "Consultas: " + ", ".join(sorted(CONSULTAS))

    def add_arguments(self, parser):
        parser.add_argument("tipo", choices=sorted(CONSULTAS))
        parser.add_argument("alvo", nargs="?", default="")

    def handle(self, *args, **o):
        fn = CONSULTAS[o["tipo"]]
        try:
            r = fn(o["alvo"]) if fn.__code__.co_argcount else fn()
        except Exception as exc:  # devolve erro estruturado para o MCP
            raise CommandError(f"{type(exc).__name__}: {exc}") from exc
        self.stdout.write(json.dumps(r, ensure_ascii=False, indent=2, default=str))
