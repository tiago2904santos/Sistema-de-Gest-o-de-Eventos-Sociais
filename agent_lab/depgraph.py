"""Mapa de dependências: imports entre apps, relações entre modelos, templates.

Saída em ``reports/architecture/``:
    dependency-graph.json   tudo (arestas com contagem, ciclos, métricas por app)
    app-imports.mmd         grafo Mermaid de imports entre apps
    model-relations.mmd     grafo Mermaid de FKs entre apps (nível de app)
    app-imports.dot         Graphviz, para quem preferir
"""

from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.apps import apps
from django.conf import settings

from .inventory import apps_projeto, arquivos, ler, templates_projeto, RE_EXTENDS, RE_INCLUDE

BASE = Path(settings.BASE_DIR)


def _modulo_de(p: Path) -> str:
    partes = list(p.relative_to(BASE).with_suffix("").parts)
    if partes[-1] == "__init__":
        partes = partes[:-1]
    return ".".join(partes)


def imports_entre_apps():
    nomes = {apps.get_app_config(lb).name: lb for lb in apps_projeto()}
    raiz_para_app = {n.split(".")[0]: lb for n, lb in nomes.items()}
    arestas = Counter()
    arestas_teste = Counter()
    modulos = defaultdict(set)
    for p in arquivos(BASE, ".py"):
        partes = p.relative_to(BASE).parts
        if partes[0] not in raiz_para_app or "migrations" in partes:
            continue
        origem = raiz_para_app[partes[0]]
        eh_teste = "tests" in partes or p.name.startswith("test")
        try:
            arvore = ast.parse(ler(p))
        except SyntaxError:
            continue
        for no in ast.walk(arvore):
            alvos = []
            if isinstance(no, ast.Import):
                alvos = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
                alvos = [no.module]
            for alvo in alvos:
                raiz = alvo.split(".")[0]
                if raiz in raiz_para_app and raiz_para_app[raiz] != origem:
                    (arestas_teste if eh_teste else arestas)[(origem, raiz_para_app[raiz])] += 1
                    if not eh_teste:
                        modulos[(origem, raiz_para_app[raiz])].add(f"{_modulo_de(p)} → {alvo}")
    return arestas, arestas_teste, modulos


def relacoes_modelos():
    arestas = Counter()
    detalhes = defaultdict(list)
    for m in apps.get_models():
        a = m._meta.app_label
        if a not in apps_projeto():
            continue
        for f in m._meta.get_fields():
            if getattr(f, "concrete", False) and f.is_relation and f.related_model:
                b = f.related_model._meta.app_label
                if b != a and b in apps_projeto():
                    arestas[(a, b)] += 1
                    detalhes[(a, b)].append(f"{m.__name__}.{f.name} → {f.related_model.__name__}")
    return arestas, detalhes


def ciclos(arestas):
    grafo = defaultdict(set)
    for a, b in arestas:
        grafo[a].add(b)
    # Tarjan: componentes fortemente conexos com mais de um nó = ciclos de dependência.
    indice, low, pilha, na_pilha, comps = {}, {}, [], set(), []
    contador = [0]

    def visitar(v):
        indice[v] = low[v] = contador[0]
        contador[0] += 1
        pilha.append(v)
        na_pilha.add(v)
        for w in sorted(grafo[v]):
            if w not in indice:
                visitar(w)
                low[v] = min(low[v], low[w])
            elif w in na_pilha:
                low[v] = min(low[v], indice[w])
        if low[v] == indice[v]:
            comp = []
            while True:
                w = pilha.pop()
                na_pilha.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                comps.append(sorted(comp))

    for v in sorted(set(grafo) | {b for s in grafo.values() for b in s}):
        if v not in indice:
            visitar(v)
    return comps


def templates_grafo():
    arestas = []
    for nome, p in templates_projeto():
        txt = ler(p)
        for e in RE_EXTENDS.findall(txt):
            arestas.append({"from": nome, "to": e, "kind": "extends"})
        for i in set(RE_INCLUDE.findall(txt)):
            arestas.append({"from": nome, "to": i, "kind": "include"})
    return arestas


def _mermaid(arestas, titulo):
    linhas = ["%% " + titulo, "graph LR"]
    for (a, b), n in sorted(arestas.items()):
        linhas.append(f"  {a} -->|{n}| {b}")
    return "\n".join(linhas) + "\n"


def gerar(destino: Path) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    imp, imp_teste, mods = imports_entre_apps()
    rel_m, det_m = relacoes_modelos()
    fan_out = Counter(a for a, _ in imp)
    fan_in = Counter(b for _, b in imp)
    metricas = {
        app: {
            "fan_out": fan_out.get(app, 0),
            "fan_in": fan_in.get(app, 0),
            # Instabilidade de Martin: 0 = estável (muitos dependem dele), 1 = instável.
            "instability": round(fan_out.get(app, 0) / ((fan_out.get(app, 0) + fan_in.get(app, 0)) or 1), 2),
        }
        for app in apps_projeto()
    }
    dados = {
        "app_imports": [
            {"from": a, "to": b, "count": n, "examples": sorted(mods[(a, b)])[:8]} for (a, b), n in sorted(imp.items())
        ],
        "app_imports_tests_only": [
            {"from": a, "to": b, "count": n} for (a, b), n in sorted(imp_teste.items()) if (a, b) not in imp
        ],
        "import_cycles": ciclos(imp),
        "model_relations": [
            {"from": a, "to": b, "count": n, "fields": det_m[(a, b)]} for (a, b), n in sorted(rel_m.items())
        ],
        "model_relation_cycles": ciclos(rel_m),
        "app_metrics": metricas,
        "template_edges": templates_grafo(),
    }
    (destino / "dependency-graph.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destino / "app-imports.mmd").write_text(_mermaid(imp, "Imports entre apps (código de produção)"), encoding="utf-8")
    (destino / "model-relations.mmd").write_text(_mermaid(rel_m, "Relações entre modelos, por app"), encoding="utf-8")
    dot = ["digraph apps { rankdir=LR; node [shape=box, fontname=Helvetica];"]
    dot += [f'  "{a}" -> "{b}" [label="{n}"];' for (a, b), n in sorted(imp.items())]
    (destino / "app-imports.dot").write_text("\n".join(dot + ["}"]) + "\n", encoding="utf-8")
    return {
        "app_import_edges": len(imp),
        "import_cycles": len(dados["import_cycles"]),
        "model_relation_edges": len(rel_m),
        "template_edges": len(dados["template_edges"]),
    }
