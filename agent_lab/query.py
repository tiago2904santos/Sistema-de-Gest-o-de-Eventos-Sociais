"""Consultas estruturadas sobre o projeto (base do project-mcp e do `manage.py agent_query`).

Cada função devolve dados JSON-serializáveis com a **fonte** de cada informação,
para o agente nunca responder sem apontar de onde tirou.
"""

from __future__ import annotations

import inspect
import json
import re
import subprocess
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.urls import Resolver404, resolve

from . import inventory as inv

BASE = Path(settings.BASE_DIR)


def _json(nome):
    arq = BASE / "ui-inventory" / f"{nome}.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None


def tabela_markdown(caminho: Path, cabecalho_contem: str | None = None):
    """Lê a primeira tabela Markdown (ou a que tem uma coluna com o texto dado)."""
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    tabelas, atual = [], []
    for linha in linhas:
        if linha.strip().startswith("|"):
            atual.append(linha)
        elif atual:
            tabelas.append(atual)
            atual = []
    if atual:
        tabelas.append(atual)
    for t in tabelas:
        if len(t) < 3:
            continue
        cab = [c.strip() for c in t[0].strip().strip("|").split("|")]
        if cabecalho_contem and not any(cabecalho_contem.lower() in c.lower() for c in cab):
            continue
        out = []
        for linha in t[2:]:
            cel = [c.strip() for c in linha.strip().strip("|").split("|")]
            out.append(dict(zip(cab, cel, strict=False)))
        return out
    return []


def _fonte(p):
    return inv.rel(p) if isinstance(p, Path) else p


def project():
    from .environment import detectar

    resumo = _json("summary") or {}
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=BASE, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        branch = None
    nav = _json("navigation") or {"modules": []}
    return {
        "name": "Sistema de Gestão de Eventos Sociais (PCPR) — base da unificação com o Central de Viagens",
        "stack": {"django": __import__("django").get_version(), "python": __import__("sys").version.split()[0]},
        "environment": detectar(),
        "git_branch": branch,
        "inventory_summary": resumo,
        "modules": [
            {"slug": m["slug"], "name": m["nome"], "access_code": m.get("codigo"), "nav_items": len(m["itens"])}
            for m in nav["modules"]
        ],
        "sources": ["ui-inventory/summary.json", "ui-inventory/navigation.json", "agent_lab/environment.py"],
        "start_here": ["CLAUDE.md", "docs/README.md", "docs/agent/memory/known-problems.md"],
    }


def route(q: str):
    rotas = inv.coletar_rotas()["routes"]
    achadas = [r for r in rotas if r["name"] == q]
    if not achadas and q.startswith("/"):
        try:
            m = resolve(q.split("?")[0])
            nome = f"{m.namespace}:{m.url_name}" if m.namespace else m.url_name
            achadas = [r for r in rotas if r["name"] == nome]
            for r in achadas:
                r["resolved_kwargs"] = m.kwargs
        except Resolver404:
            return {"error": f"Nenhuma rota resolve {q}"}
    if not achadas:
        achadas = [r for r in rotas if q.lower() in (r["name"] or "").lower() or q.lower() in r["pattern"].lower()][:25]
        return {
            "matches": [{"name": r["name"], "pattern": r["pattern"]} for r in achadas],
            "hint": "use o nome exato ou um caminho",
        }
    r = achadas[0]
    fonte = ""
    if r.get("file") and r.get("line"):
        linhas = (BASE / r["file"]).read_text(encoding="utf-8").splitlines()
        fonte = "\n".join(linhas[r["line"] - 1 : r["line"] + 39])
    return {**r, "view_source_head": fonte, "sources": [f"{r.get('file')}:{r.get('line')}", "ui-inventory/routes.json"]}


def page(q: str):
    paginas = inv.coletar_templates(inv.coletar_rotas())[1]["pages"]
    alvo = q
    if q.startswith("/"):
        r = route(q)
        tpls = r.get("templates") or []
        if not tpls:
            return {"route": r, "error": "rota sem template identificado (view pode montar dinamicamente)"}
        alvo = tpls[0]
    p = next((x for x in paginas if x["template"] == alvo), None)
    if not p:
        return {"matches": [x["template"] for x in paginas if q.lower() in x["template"]][:25]}
    estados = next((s for s in (_json("states") or {}).get("pages", []) if s["template"] == alvo), None)
    arquetipo = None
    pages_ts = BASE / "tests" / "support" / "pages.ts"
    if pages_ts.exists():
        for m in re.finditer(
            r'path: "([^"]+)", role: "(\w+)", archetype: "(\w+)"', pages_ts.read_text(encoding="utf-8")
        ):
            if q == m.group(1):
                arquetipo = {"archetype": m.group(3), "role": m.group(2)}
    comps = [i for i in p["includes"] if i.startswith("components/")]
    return {
        **p,
        "components": comps,
        "states": estados,
        "key_page": arquetipo,
        "sources": [p["file"], "ui-inventory/pages.json"],
    }


def component(q: str):
    comps = inv.coletar_componentes(inv.coletar_templates(inv.coletar_rotas())[2])["template_components"]
    c = next(
        (
            x
            for x in comps
            if x["template"] == q or x["template"].endswith("/" + q) or x["template"].endswith("/" + q + ".html")
        ),
        None,
    )
    if not c:
        return {"matches": [x["template"] for x in comps if q.lower() in x["template"]]}
    txt = (BASE / c["file"]).read_text(encoding="utf-8")
    m = re.search(r"{%\s*comment\s*%}(.*?){%\s*endcomment\s*%}", txt, re.S)
    from .specimens import all_specimens

    especimes = [s.id for s in all_specimens() if s.component == c["template"]]
    return {
        **c,
        "contract": m.group(1).strip() if m else None,
        "specimens": especimes,
        "lab_urls": [f"/_lab/c/{s}/" for s in especimes],
        "sources": [c["file"], "agent_lab/specimens.py"],
    }


def form(q: str):
    forms = inv.coletar_forms()["forms"]
    f = next((x for x in forms if x["form"] == q or x["form"].endswith("." + q)), None)
    if not f:
        return {"matches": [x["form"] for x in forms if q.lower() in x["form"].lower()][:25]}
    classe = f["form"].rsplit(".", 1)[1]
    usos = []
    for p in inv.arquivos(BASE, ".py"):
        if "views" in p.name and re.search(rf"\b{classe}\b", inv.ler(p)):
            usos.append(inv.rel(p))
    return {**f, "used_in": usos, "sources": ["ui-inventory/forms.json"] + usos}


def model(q: str):
    try:
        m = apps.get_model(q) if "." in q else next(x for x in apps.get_models() if x.__name__.lower() == q.lower())
    except LookupError, StopIteration:
        return {"matches": [x._meta.label for x in apps.get_models() if q.lower() in x._meta.label.lower()]}
    ent = next(e for e in inv.coletar_entidades(com_contagem=False)["entities"] if e["model"] == m._meta.label)
    entrada = [
        f"{r.related_model._meta.label}.{r.field.name} ({r.on_delete.__name__ if r.on_delete else 'm2m'})"
        for r in m._meta.related_objects
        if hasattr(r, "field")
    ]
    try:
        arquivo = inv.rel(inspect.getsourcefile(m))
    except TypeError:
        arquivo = None
    return {**ent, "referenced_by": sorted(entrada), "sources": [arquivo, "ui-inventory/entities.json"]}


def permission(q: str):
    from accounts.modulos import MODULOS_PORTAL, NAMESPACES_MODULOS

    from .seed import PAPEIS

    codigo = NAMESPACES_MODULOS.get(q) or (q if q in set(NAMESPACES_MODULOS.values()) else None)
    papeis = []
    for username, grupos, mods, superuser, _ in PAPEIS:
        acesso = superuser or (codigo is None) or (mods == "*" or codigo in (mods or []))
        papeis.append({"user": username, "groups": grupos, "has_module": acesso})
    return {
        "query": q,
        "module_code": codigo,
        "namespaces": sorted(ns for ns, c in NAMESPACES_MODULOS.items() if c == codigo) if codigo else [q],
        "portal": [m["nome"] for m in MODULOS_PORTAL.values() if m.get("codigo") == codigo],
        "lab_roles": papeis,
        "note": "Sem código = módulo aberto a autenticados; grupos refinam ações dentro das views (ex.: VIAGENS_GESTOR p/ diárias).",
        "sources": ["accounts/modulos.py", "agent_lab/seed.py (PAPEIS)"],
    }


def integration(q: str = ""):
    d = inv.coletar_integracoes()
    if q:
        d["known"] = [k for k in d["known"] if q.lower() in k["name"].lower() or q.lower() in k["settings"].lower()]
    return {**d, "sources": ["config/settings.py", ".env.example", "docs/integrations/README.md"]}


def document(q: str = ""):
    d = inv.coletar_documentos()
    if q:
        d["types"] = [
            t for t in d.get("types", []) if q.lower() in t["tipo"].lower() or q.lower() in t["label"].lower()
        ]
    return {**d, "sources": ["documentos/services/registry.py", "documentos/resources/"]}


def tokens(categoria: str = ""):
    t = _json("tokens") or inv.coletar_tokens()
    lista = [x for x in t["tokens"] if not categoria or x["category"] == categoria]
    contraste = BASE / "reports" / "design" / "contrast.md"
    return {
        "count": len(lista),
        "tokens": lista,
        "used_but_undefined": t.get("used_but_undefined"),
        "v4_tokens": sorted(p.name for p in (BASE / "tokens").glob("*.json")),
        "contrast_report": inv.rel(contraste) if contraste.exists() else "rode npm run agent:tokens",
        "sources": ["ui-inventory/tokens.json", "tokens/*.json", "docs/design-system/colors.md"],
    }


def archetypes():
    doc = BASE / "docs" / "design-system" / "page-archetypes.md"
    return {"archetypes": tabela_markdown(doc, "Arquétipo"), "sources": [inv.rel(doc), "tests/support/pages.ts"]}


def known_problems(severidade: str = ""):
    doc = BASE / "docs" / "agent" / "memory" / "known-problems.md"
    linhas = tabela_markdown(doc, "Sev")
    if severidade:
        linhas = [x for x in linhas if severidade.upper() in x.get("Sev.", "")]
    return {"count": len(linhas), "problems": linhas, "sources": [inv.rel(doc)]}


def migration_status(modulo: str = ""):
    doc = BASE / "docs" / "architecture" / "migration-matrix.md"
    linhas = tabela_markdown(doc, "Módulo")
    if modulo:
        linhas = [x for x in linhas if modulo.lower() in x.get("Módulo", "").lower()]
    return {"modules": linhas, "sources": [inv.rel(doc)]}


def component_usage(q: str):
    c = component(q)
    return {k: c.get(k) for k in ("template", "used_by_count", "used_by", "sources", "matches") if k in c}


def duplicates():
    return {**(_json("duplication-report") or {}), "sources": ["ui-inventory/duplication-report.json"]}


def dependency_graph(app: str = ""):
    arq = BASE / "reports" / "architecture" / "dependency-graph.json"
    if not arq.exists():
        from .depgraph import gerar

        gerar(arq.parent)
    d = json.loads(arq.read_text(encoding="utf-8"))
    if app:
        d["app_imports"] = [e for e in d["app_imports"] if app in (e["from"], e["to"])]
        d["model_relations"] = [e for e in d["model_relations"] if app in (e["from"], e["to"])]
        d["app_metrics"] = {app: d["app_metrics"].get(app)}
    d.pop("template_edges", None)
    return {**d, "sources": [inv.rel(arq)]}


CONSULTAS = {
    "project": project,
    "route": route,
    "page": page,
    "component": component,
    "form": form,
    "model": model,
    "permission": permission,
    "integration": integration,
    "document": document,
    "tokens": tokens,
    "archetypes": archetypes,
    "known_problems": known_problems,
    "migration_status": migration_status,
    "component_usage": component_usage,
    "duplicates": duplicates,
    "dependency_graph": dependency_graph,
}
