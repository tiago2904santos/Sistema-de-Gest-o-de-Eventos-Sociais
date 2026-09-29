"""Inteligência de banco: explain | migrations | anomalies | indexes | env."""

import json

from django.core.management.base import BaseCommand, CommandError

from agent_lab import db_intel
from agent_lab.environment import detectar


class Command(BaseCommand):
    help = "agent_db explain '<SELECT …>' [--analyze] | migrations | anomalies | indexes | env"

    def add_arguments(self, parser):
        parser.add_argument("acao", choices=["explain", "migrations", "anomalies", "indexes", "env"])
        parser.add_argument("sql", nargs="?", default="")
        parser.add_argument("--analyze", action="store_true")

    def handle(self, *args, **o):
        try:
            r = {
                "explain": lambda: db_intel.explain(o["sql"], analyze=o["analyze"]),
                "migrations": db_intel.migracoes,
                "anomalies": db_intel.anomalias,
                "indexes": db_intel.indices,
                "env": detectar,
            }[o["acao"]]()
        except db_intel.ConsultaRecusada as exc:
            raise CommandError(f"Recusado: {exc}") from exc
        self.stdout.write(json.dumps(r, ensure_ascii=False, indent=2, default=str))
