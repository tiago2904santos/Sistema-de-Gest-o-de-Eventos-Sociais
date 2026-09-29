"""Auditoria de banco: estrutura (sempre) e dados (quando há banco com dados).

``python manage.py agent_db_audit [--dados]`` → reports/data/db-audit.{json,md}

Estrutura: relações e on_delete (cascatas perigosas), constraints e índices declarados,
campos legados, FKs anuláveis, modelos sem ordering (paginação instável).
Dados (--dados): linhas por tabela, duplicidades em chaves naturais conhecidas,
referências "soltas" (ids em JSON/Char que apontam para registros inexistentes não
são detectáveis genericamente — ficam listados como pontos a verificar).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from django.apps import apps
from django.db import models
from django.db.models import Count

from .inventory import apps_projeto

# Chaves naturais que não deveriam repetir (modelo, campos).
CHAVES_NATURAIS = [
    ("viagens_cadastros.Servidor", ("nome",)),
    ("cadastros.Municipio", ("nome", "estado")),
    ("viagens_cadastros.Unidade", ("nome",)),
    ("coffee_break.Fornecedor", ("razao_social",)),
    ("publicacoes.Responsavel", ("nome",)),
]


def estrutura():
    cascatas, anulaveis, legados, sem_ordering, constraints, indices = [], [], [], [], {}, {}
    for m in apps.get_models():
        if m._meta.app_label not in apps_projeto():
            continue
        label = m._meta.label
        if not m._meta.ordering:
            sem_ordering.append(label)
        if m._meta.constraints:
            constraints[label] = [c.name for c in m._meta.constraints]
        if m._meta.indexes:
            indices[label] = [i.name for i in m._meta.indexes]
        for f in m._meta.concrete_fields:
            if f.name.startswith("legado_"):
                legados.append(f"{label}.{f.name}")
            if isinstance(f, models.ForeignKey):
                alvo = f.related_model._meta.label
                if f.remote_field.on_delete is models.CASCADE and alvo in (
                    "accounts.User",
                    "cadastros.Municipio",
                    "viagens_cadastros.Servidor",
                ):
                    cascatas.append(f"{label}.{f.name} → {alvo} (CASCADE)")
                if f.null:
                    anulaveis.append(f"{label}.{f.name} → {alvo}")
    return {
        "risky_cascades": sorted(cascatas),
        "nullable_fks": len(anulaveis),
        "legacy_fields": sorted(legados),
        "models_without_ordering": sorted(sem_ordering),
        "check_and_unique_constraints": constraints,
        "declared_indexes": indices,
    }


def dados():
    linhas = {}
    for m in apps.get_models():
        if m._meta.app_label in apps_projeto():
            linhas[m._meta.label] = m._default_manager.count()
    duplicidades = {}
    for label, campos in CHAVES_NATURAIS:
        m = apps.get_model(label)
        dup = m._default_manager.values(*campos).annotate(n=Count("pk")).filter(n__gt=1).order_by("-n")[:20]
        if dup:
            duplicidades[f"{label}({','.join(campos)})"] = [dict(d) for d in dup]
    return {
        "row_counts": linhas,
        "empty_tables": sorted(k for k, v in linhas.items() if v == 0),
        "natural_key_duplicates": duplicidades,
    }


def executar(destino: Path, com_dados=False):
    destino.mkdir(parents=True, exist_ok=True)
    r = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "structure": estrutura()}
    if com_dados:
        r["data"] = dados()
    (destino / "db-audit.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    s = r["structure"]
    md = [
        "# Auditoria de banco",
        "",
        f"Gerado em {r['generated_at']}.",
        "",
        f"- Cascatas sensíveis (apagar usuário/município/servidor apaga dependentes): **{len(s['risky_cascades'])}**",
        f"- FKs anuláveis: {s['nullable_fks']}",
        f"- Campos de rastreio do legado (`legado_*`): {len(s['legacy_fields'])}",
        f"- Modelos sem `ordering` (paginação pode oscilar): {len(s['models_without_ordering'])}",
        f"- Modelos com constraints declaradas: {len(s['check_and_unique_constraints'])}",
        "",
        "## Cascatas sensíveis",
        "",
        *[f"- {c}" for c in s["risky_cascades"]],
    ]
    if com_dados:
        d = r["data"]
        md += [
            "",
            "## Dados",
            "",
            f"- Tabelas vazias: {len(d['empty_tables'])}",
            f"- Duplicidades em chaves naturais: {len(d['natural_key_duplicates'])}",
        ]
        md += [f"  - {k}: {len(v)} grupo(s)" for k, v in d["natural_key_duplicates"].items()]
    (destino / "db-audit.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {
        "risky_cascades": len(s["risky_cascades"]),
        "models_without_ordering": len(s["models_without_ordering"]),
        "with_data": com_dados,
    }
