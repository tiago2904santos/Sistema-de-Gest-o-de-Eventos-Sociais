"""Inteligência de banco: EXPLAIN seguro, validação de migrações, anomalias e índices.

Tudo aqui respeita o ambiente (``agent_lab/environment.py``): leitura em qualquer
ambiente, mas EXPLAIN ANALYZE (que executa a consulta) só em LAB/DEV, e sempre
dentro de transação somente-leitura.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor

from .environment import detectar
from .inventory import apps_projeto

BASE = Path(settings.BASE_DIR)
PROIBIDAS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|vacuum|call|do|merge|lock|set)\b", re.I
)


class ConsultaRecusada(Exception):
    pass


def validar_select(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise ConsultaRecusada("uma instrução por vez")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise ConsultaRecusada("só SELECT/WITH")
    if PROIBIDAS.search(re.sub(r"'[^']*'", "''", s)):
        raise ConsultaRecusada("palavra-chave de escrita/DDL encontrada")
    return s


def explain(sql: str, *, analyze=False):
    s = validar_select(sql)
    amb = detectar()["environment"]
    if analyze and amb not in ("LAB", "DEV"):
        raise ConsultaRecusada(f"ANALYZE executa a consulta: só em LAB/DEV (atual: {amb})")
    with transaction.atomic():
        with connection.cursor() as c:
            if connection.vendor == "postgresql":
                c.execute("SET TRANSACTION READ ONLY")
                c.execute(f"EXPLAIN (FORMAT TEXT{', ANALYZE, BUFFERS' if analyze else ''}) {s}")
            elif connection.vendor == "sqlite":
                c.execute("PRAGMA query_only = ON")
                try:
                    c.execute(f"EXPLAIN QUERY PLAN {s}")
                    linhas = [" | ".join(str(x) for x in row) for row in c.fetchall()]
                finally:
                    c.execute("PRAGMA query_only = OFF")
            else:
                c.execute(f"EXPLAIN {s}")
            if connection.vendor != "sqlite":
                linhas = [" | ".join(str(x) for x in row) for row in c.fetchall()]
        transaction.set_rollback(True)
    plano = "\n".join(linhas)
    alertas = []
    if re.search(r"Seq Scan|SCAN (TABLE )?\w+(?! USING)", plano) and not re.search(r"USING (COVERING )?INDEX", plano):
        alertas.append("varredura sequencial — verifique índice nas colunas de filtro/junção")
    return {"environment": amb, "vendor": connection.vendor, "analyze": analyze, "plan": plano, "alerts": alertas}


DESTRUTIVAS = ("RemoveField", "DeleteModel", "RemoveConstraint", "RemoveIndex", "RenameField", "RenameModel", "RunSQL")


def migracoes():
    executor = MigrationExecutor(connection)
    plano = executor.migration_plan(executor.loader.graph.leaf_nodes())
    pendentes = []
    for mig, _ in plano:
        ops = [type(op).__name__ for op in mig.operations]
        pendentes.append(
            {
                "migration": f"{mig.app_label}.{mig.name}",
                "operations": ops,
                "destructive": sorted({o for o in ops if o in DESTRUTIVAS}),
                "data_migration": any(o in ("RunPython",) for o in ops),
            }
        )
    check = subprocess.run(
        [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
        cwd=BASE,
        capture_output=True,
        text=True,
        timeout=180,
    )
    conflitos = executor.loader.detect_conflicts()
    return {
        "unapplied": pendentes,
        "models_without_migration": check.returncode != 0,
        "makemigrations_output": (check.stdout + check.stderr).strip()[-1500:],
        "conflicts": {k: v for k, v in conflitos.items()},
        "advice": "Migrações destrutivas ou RunPython pendentes exigem backup e ensaio em cópia (docs/data/README.md).",
    }


PARES_DATA = [
    ("data_inicio_evento", "data_fim_evento"),
    ("vigencia_inicio", "vigencia_fim"),
    ("data_inicio", "data_fim"),
    ("saida_dt", "chegada_dt"),
    ("data_evento_inicio", "data_evento_fim"),
]


def anomalias(limite=20):
    from django.db.models import F, Q

    out = []
    for m in apps.get_models():
        if m._meta.app_label not in apps_projeto():
            continue
        nomes = {f.name for f in m._meta.concrete_fields}
        for ini, fim in PARES_DATA:
            if ini in nomes and fim in nomes:
                n = m._default_manager.filter(**{f"{fim}__lt": F(ini)}).count()
                if n:
                    out.append({"model": m._meta.label, "check": f"{fim} < {ini}", "rows": n})
        for f in m._meta.concrete_fields:
            if f.get_internal_type() in ("DecimalField", "FloatField", "IntegerField") and not f.name.endswith(
                ("_pk", "id")
            ):
                if re.search(r"(valor|quantidade|km|distancia|total)", f.name):
                    n = m._default_manager.filter(**{f"{f.name}__lt": 0}).count()
                    if n:
                        out.append({"model": m._meta.label, "check": f"{f.name} negativo", "rows": n})
            if f.get_internal_type() == "CharField" and not f.blank and not f.null and not f.has_default():
                n = m._default_manager.filter(Q(**{f.name: ""})).count()
                if n:
                    out.append({"model": m._meta.label, "check": f"{f.name} obrigatório vazio", "rows": n})
    return {"environment": detectar()["environment"], "anomalies": out[: limite * 5]}


def indices(min_linhas=1000):
    """Tabelas grandes e as colunas de FK/ordenação sem índice declarado ou implícito."""
    sugestoes = []
    with connection.cursor() as c:
        for m in apps.get_models():
            if m._meta.app_label not in apps_projeto():
                continue
            tabela = m._meta.db_table
            try:
                cons = connection.introspection.get_constraints(c, tabela)
            except Exception:
                continue
            indexadas = {
                tuple(v["columns"])[0]
                for v in cons.values()
                if v.get("columns") and (v.get("index") or v.get("unique") or v.get("primary_key"))
            }
            try:
                linhas = m._default_manager.count()
            except Exception:
                linhas = None
            for campo in m._meta.ordering or []:
                col = campo.lstrip("-").split("__")[0]
                try:
                    coluna = m._meta.get_field(col).column
                except Exception:
                    continue
                if coluna not in indexadas:
                    sugestoes.append(
                        {"table": tabela, "column": coluna, "reason": "usada no ordering padrão", "rows": linhas}
                    )
    grandes = [s for s in sugestoes if (s["rows"] or 0) >= min_linhas]
    return {
        "ordering_without_index": sugestoes,
        "large_tables_affected": grandes,
        "note": "Com poucos dados o impacto é nulo; rode com o cenário very_large para medir.",
    }
