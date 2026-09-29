"""Inventário do produto gerado por introspecção (Django + varredura de arquivos).

Uso: ``python manage.py agent_inventory`` → grava ``ui-inventory/*.json``.

Cada coletor é independente e tolerante a falhas: se um quebrar, o arquivo dele
sai com ``{"error": ...}`` e os outros continuam. A saída é determinística
(ordenada), para que o diff do inventário entre dois commits seja legível.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver

BASE = Path(settings.BASE_DIR)
TEMPLATES_DIR = BASE / "templates"
STATIC_DIR = BASE / "static"
IGNORAR_DIRS = {".venv", "node_modules", "staticfiles", ".git", "media", "__pycache__", "vendor"}
APPS_PROJETO = None  # preenchido sob demanda


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------


def rel(p: Path | str) -> str:
    try:
        return str(Path(p).resolve().relative_to(BASE))
    except ValueError:
        return str(p)


def apps_projeto():
    global APPS_PROJETO
    if APPS_PROJETO is None:
        APPS_PROJETO = sorted(
            c.label
            for c in apps.get_app_configs()
            if Path(c.path).resolve().is_relative_to(BASE) and ".venv" not in Path(c.path).parts
        )
    return APPS_PROJETO


def arquivos(raiz: Path, sufixo: str):
    for p in sorted(raiz.rglob(f"*{sufixo}")):
        if IGNORAR_DIRS & set(p.relative_to(BASE).parts):
            continue
        yield p


def ler(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="latin-1")


def templates_projeto():
    out = []
    raizes = [TEMPLATES_DIR] + [Path(apps.get_app_config(a).path) / "templates" for a in apps_projeto()]
    for raiz in raizes:
        if raiz.is_dir():
            for p in arquivos(raiz, ".html"):
                out.append((p.relative_to(raiz).as_posix(), p))
    return sorted(set(out))


# ---------------------------------------------------------------------------
# rotas
# ---------------------------------------------------------------------------


def _walk(resolvers, prefix="", ns=None):
    for entry in resolvers:
        if isinstance(entry, URLResolver):
            novo_ns = ns
            if entry.namespace:
                novo_ns = f"{ns}:{entry.namespace}" if ns else entry.namespace
            yield from _walk(entry.url_patterns, prefix + str(entry.pattern), novo_ns)
        elif isinstance(entry, URLPattern):
            yield prefix + str(entry.pattern), ns, entry


def _view_info(callback):
    view = getattr(callback, "view_class", None) or getattr(callback, "cls", None) or callback
    alvo = inspect.unwrap(view)
    modulo = getattr(alvo, "__module__", "?")
    nome = getattr(alvo, "__qualname__", getattr(alvo, "__name__", repr(alvo)))
    arquivo, linha = None, None
    try:
        arquivo = rel(inspect.getsourcefile(alvo))
        linha = inspect.getsourcelines(alvo)[1]
    except TypeError, OSError:
        pass
    fonte = ""
    try:
        fonte = inspect.getsource(alvo)
    except TypeError, OSError:
        pass
    # Decorators deixam rastro em __wrapped__/atributos; olhamos a fonte do wrapper também.
    decorators = set()
    cadeia = callback
    while cadeia is not None:
        nomeq = getattr(cadeia, "__qualname__", "")
        if "login_required" in nomeq:
            decorators.add("login_required")
        cadeia = getattr(cadeia, "__wrapped__", None)
    for linha_src in fonte.splitlines():
        if re.match(r"\s*(async\s+)?(def|class)\s", linha_src):
            break
        m = re.match(r"\s*@([\w\.]+)", linha_src)
        if m:
            decorators.add(m.group(1).split(".")[-1])
    for mixin in getattr(view, "__mro__", ()):
        if mixin.__name__.endswith("Mixin"):
            decorators.add(mixin.__name__)
    templates = sorted(
        set(
            re.findall(
                r"[\"']((?:pages|components|layouts|documentos|coffee_break|agent_lab)/[\w\-/\.]+\.html)[\"']", fonte
            )
        )
    )
    tn = getattr(view, "template_name", None)
    if isinstance(tn, str):
        templates = sorted(set(templates) | {tn})
    metodos = sorted(
        set(re.findall(r"request\.method\s*==\s*[\"'](\w+)", fonte)) | set(re.findall(r"require_(GET|POST)", fonte))
    )
    return {
        "view": f"{modulo}.{nome}",
        "file": arquivo,
        "line": linha,
        "decorators": sorted(decorators),
        "templates": templates,
        "methods_hint": metodos,
    }


def coletar_rotas():
    try:
        from accounts.modulos import NAMESPACES_MODULOS
    except Exception:  # pragma: no cover
        NAMESPACES_MODULOS = {}
    rotas = []
    for padrao, ns, entry in _walk(get_resolver().url_patterns):
        nome = entry.name
        full = f"{ns}:{nome}" if ns and nome else nome
        info = _view_info(entry.callback)
        raiz_ns = (ns or "").split(":")[0]
        publico = raiz_ns in {"accounts"} and nome in {"login", "logout"}
        padrao_limpo = "/" + re.sub(r"\^|\$|\\Z", "", padrao)
        rotas.append(
            {
                "name": full,
                "pattern": padrao_limpo,
                "namespace": ns,
                "params": re.findall(r"<(?:\w+:)?(\w+)>", padrao),
                "module_code": NAMESPACES_MODULOS.get(raiz_ns),
                "public_hint": publico
                or raiz_ns in {"demandas_eventos_publico", "coffee_break_publico"}
                or padrao_limpo.startswith(("/pedido", "/fornecedor")),
                "admin": padrao_limpo.startswith("/admin"),
                **info,
            }
        )
    rotas.sort(key=lambda r: (r["pattern"], r["name"] or ""))
    return {"count": len(rotas), "routes": rotas}


# ---------------------------------------------------------------------------
# templates: páginas e componentes
# ---------------------------------------------------------------------------

RE_EXTENDS = re.compile(r"{%\s*extends\s+[\"']([^\"']+)[\"']")
RE_INCLUDE = re.compile(r"{%\s*include\s+[\"']([^\"']+)[\"']")
RE_BLOCK = re.compile(r"{%\s*block\s+(\w+)")
RE_STATIC = re.compile(r"{%\s*static\s+[\"']([^\"']+)[\"']")
RE_LOAD = re.compile(r"{%\s*load\s+([\w\s]+?)\s*%}")
RE_PARTIALDEF = re.compile(r"{%\s*partialdef\s+([\w\-]+)")


def _analisar_template(nome, caminho):
    txt = ler(caminho)
    return {
        "template": nome,
        "file": rel(caminho),
        "lines": txt.count("\n") + 1,
        "extends": RE_EXTENDS.findall(txt),
        "includes": sorted(set(RE_INCLUDE.findall(txt))),
        "blocks": sorted(set(RE_BLOCK.findall(txt))),
        "static": sorted(set(RE_STATIC.findall(txt))),
        "loads": sorted({t for grupo in RE_LOAD.findall(txt) for t in grupo.split()}),
        "partials": RE_PARTIALDEF.findall(txt),
        "inline_style_attrs": len(re.findall(r"\sstyle=\"", txt)),
        "inline_script_blocks": len(re.findall(r"<script(?![^>]*\bsrc=)", txt)),
        "has_table": "<table" in txt,
        "has_form": "<form" in txt,
        "has_dialog": bool(re.search(r"<dialog|role=\"dialog\"|class=\"[^\"]*\bmodal\b", txt)),
        "has_empty_state": bool(re.search(r"{%\s*empty\s*%}|estado-vazio|empty-state|vazio|Nenhum|Nenhuma", txt)),
        "sha1_normalized": hashlib.sha1(re.sub(r"\s+", " ", txt).encode()).hexdigest(),
    }


def coletar_templates(rotas):
    usados_por_rota = defaultdict(list)
    for r in rotas["routes"]:
        for t in r["templates"]:
            usados_por_rota[t].append(r["name"])
    paginas, componentes, layouts, outros = [], [], [], []
    todos = []
    for nome, caminho in templates_projeto():
        info = _analisar_template(nome, caminho)
        todos.append(info)
        if nome.startswith("components/") or "/components/" in nome or nome.startswith("partials/"):
            componentes.append(info)
        elif nome.startswith("layouts/"):
            layouts.append(info)
        elif nome.startswith("pages/") or nome in {"403.html", "404.html", "500.html"}:
            info["routes"] = sorted(usados_por_rota.get(nome, []))
            paginas.append(info)
        else:
            outros.append(info)
    uso = Counter()
    usado_em = defaultdict(set)
    for t in todos:
        for inc in t["includes"]:
            uso[inc] += 1
            usado_em[inc].add(t["template"])
    for c in componentes:
        c["used_by_count"] = uso.get(c["template"], 0)
        c["used_by"] = sorted(usado_em.get(c["template"], set()))
    return todos, {"count": len(paginas), "pages": paginas, "layouts": layouts, "other_templates": outros}, componentes


def coletar_componentes(componentes):
    # Template tags customizadas (inclusion/simple tags) também são componentes.
    tags = []
    for label in apps_projeto():
        pasta = Path(apps.get_app_config(label).path) / "templatetags"
        for p in arquivos(pasta, ".py") if pasta.is_dir() else []:
            txt = ler(p)
            for m in re.finditer(r"@register\.(inclusion_tag|simple_tag|filter|tag)\(([^)]*)\)\s*\ndef\s+(\w+)", txt):
                tags.append({"kind": m.group(1), "name": m.group(3), "file": rel(p), "args": m.group(2).strip()})
            for m in re.finditer(r"@register\.(filter|simple_tag|tag)\s*\ndef\s+(\w+)", txt):
                tags.append({"kind": m.group(1), "name": m.group(2), "file": rel(p), "args": ""})
    js = []
    comp_js = STATIC_DIR / "js" / "components"
    for p in arquivos(comp_js, ".js") if comp_js.is_dir() else []:
        js.append({"file": rel(p), "lines": ler(p).count("\n") + 1})
    return {
        "template_components": sorted(componentes, key=lambda c: c["template"]),
        "template_tags": sorted(tags, key=lambda t: (t["file"], t["name"])),
        "js_components": js,
        "unused_template_components": sorted(c["template"] for c in componentes if c["used_by_count"] == 0),
    }


def coletar_tabelas_modais(todos):
    tabelas, modais = [], []
    for t in todos:
        txt = ler(BASE / t["file"])
        for m in re.finditer(r"<table\b[^>]*>(.*?)</table>", txt, re.S):
            cab = [
                re.sub(r"<[^>]+>|{[{%].*?[}%]}", "", th).strip()
                for th in re.findall(r"<th\b[^>]*>(.*?)</th>", m.group(1), re.S)
            ]
            tabelas.append(
                {
                    "template": t["template"],
                    "file": t["file"],
                    "headers": [h for h in cab if h],
                    "has_caption": "<caption" in m.group(1),
                    "th_scope": 'scope="' in m.group(1),
                    "responsive_wrapper_hint": bool(
                        re.search(
                            r"(table-wrap|tabela-wrap|overflow|rolagem)", txt[max(0, m.start() - 300) : m.start()]
                        )
                    ),
                }
            )
        for m in re.finditer(
            r"<dialog\b[^>]*>|<[^>]+role=\"dialog\"[^>]*>|<div[^>]+class=\"[^\"]*\bmodal\b[^\"]*\"[^>]*>", txt
        ):
            tag = m.group(0)
            modais.append(
                {
                    "template": t["template"],
                    "file": t["file"],
                    "element": "dialog" if tag.startswith("<dialog") else "div",
                    "id": (re.search(r"id=\"([^\"]+)\"", tag) or [None, None])[1],
                    "aria_labelledby": "aria-labelledby" in tag,
                    "aria_modal": "aria-modal" in tag,
                }
            )
    return {"count": len(tabelas), "tables": tabelas}, {"count": len(modais), "dialogs": modais}


# ---------------------------------------------------------------------------
# formulários
# ---------------------------------------------------------------------------


def coletar_forms():
    from django import forms as djforms
    import importlib
    import pkgutil

    saida = []
    for label in apps_projeto():
        cfg = apps.get_app_config(label)
        candidatos = []
        for sub in ("forms",):
            try:
                mod = importlib.import_module(f"{cfg.name}.{sub}")
                candidatos.append(mod)
                if hasattr(mod, "__path__"):
                    for info in pkgutil.iter_modules(mod.__path__):
                        candidatos.append(importlib.import_module(f"{cfg.name}.{sub}.{info.name}"))
            except ImportError:
                continue
        for mod in candidatos:
            for nome, cls in inspect.getmembers(mod, inspect.isclass):
                if cls.__module__ != mod.__name__ or not issubclass(cls, (djforms.BaseForm, djforms.BaseFormSet)):
                    continue
                campos = []
                for fnome, f in getattr(cls, "base_fields", {}).items():
                    campos.append(
                        {
                            "name": fnome,
                            "type": type(f).__name__,
                            "widget": type(f.widget).__name__,
                            "required": f.required,
                            "label": str(f.label) if f.label else None,
                            "help_text": bool(f.help_text),
                        }
                    )
                saida.append(
                    {
                        "form": f"{mod.__name__}.{nome}",
                        "app": label,
                        "kind": "formset"
                        if issubclass(cls, djforms.BaseFormSet)
                        else ("modelform" if issubclass(cls, djforms.BaseModelForm) else "form"),
                        "model": getattr(getattr(cls, "_meta", None), "model", None) and cls._meta.model._meta.label,
                        "fields": campos,
                    }
                )
    saida.sort(key=lambda f: f["form"])
    return {"count": len(saida), "forms": saida}


# ---------------------------------------------------------------------------
# entidades
# ---------------------------------------------------------------------------


def coletar_entidades(com_contagem=True):
    ents = []
    for m in apps.get_models():
        if m._meta.app_label not in apps_projeto():
            continue
        campos = []
        for f in m._meta.get_fields():
            if f.auto_created and not f.concrete:
                continue
            item = {
                "name": f.name,
                "type": f.get_internal_type() if hasattr(f, "get_internal_type") else type(f).__name__,
            }
            if getattr(f, "is_relation", False) and f.related_model:
                item["to"] = f.related_model._meta.label
                item["relation"] = "m2m" if f.many_to_many else ("o2o" if f.one_to_one else "fk")
                on_delete = getattr(getattr(f, "remote_field", None), "on_delete", None)
                if on_delete:
                    item["on_delete"] = on_delete.__name__
            if getattr(f, "choices", None):
                item["choices"] = [str(c[0]) for c in f.choices]
            if getattr(f, "concrete", False):
                item["null"] = f.null
                item["blank"] = f.blank
                item["unique"] = f.unique
                item["db_index"] = f.db_index
                item["required"] = not f.null and not f.blank and not f.has_default() and not f.primary_key
            campos.append(item)
        ent = {
            "model": m._meta.label,
            "db_table": m._meta.db_table,
            "verbose_name": str(m._meta.verbose_name),
            "abstract_bases": [
                b.__name__ for b in m.__mro__[1:] if getattr(getattr(b, "_meta", None), "abstract", False)
            ],
            "fields": campos,
            "constraints": [c.name for c in m._meta.constraints],
            "indexes": [i.name for i in m._meta.indexes],
            "ordering": list(m._meta.ordering or []),
            "unique_together": [list(u) for u in m._meta.unique_together],
        }
        if com_contagem:
            try:
                ent["row_count"] = m._default_manager.using("default").count()
            except Exception as exc:  # banco fora do ar não derruba o inventário
                ent["row_count"] = f"erro: {type(exc).__name__}"
        ents.append(ent)
    ents.sort(key=lambda e: e["model"])
    return {"count": len(ents), "entities": ents}


# ---------------------------------------------------------------------------
# permissões, navegação, integrações, documentos
# ---------------------------------------------------------------------------


def coletar_permissoes(rotas):
    from django.contrib.auth.models import Group
    from accounts.modulos import MODULOS_PORTAL, NAMESPACES_MODULOS

    grupos_codigo = set()
    for p in arquivos(BASE, ".py"):
        if "migrations" in p.parts or "agent_lab" in p.parts:
            continue
        grupos_codigo |= set(re.findall(r"GRUPO_\w+\s*=\s*[\"']([A-Z_]+)[\"']", ler(p)))
    try:
        grupos_db = sorted(Group.objects.values_list("name", flat=True))
    except Exception:
        grupos_db = []
    try:
        from accounts.models import Modulo

        modulos_db = [{"codigo": m.codigo, "nome": m.nome, "ativo": m.ativo} for m in Modulo.objects.order_by("codigo")]
    except Exception:
        modulos_db = []
    sem_protecao = [
        r["name"] or r["pattern"]
        for r in rotas["routes"]
        if not r["admin"]
        and not r["module_code"]
        and not r["public_hint"]
        and not (
            {
                "login_required",
                "LoginRequiredMixin",
                "modulo_requerido",
                "acesso_ao_modulo",
                "gerenciamento_de_cadastros",
                "permission_required",
                "user_passes_test",
                "staff_member_required",
            }
            & set(r["decorators"])
        )
    ]
    return {
        "namespaces_to_module": dict(sorted(NAMESPACES_MODULOS.items())),
        "modules_in_portal": sorted(MODULOS_PORTAL),
        "modules_in_db": modulos_db,
        "groups_in_code": sorted(grupos_codigo),
        "groups_in_db": grupos_db,
        "routes_without_explicit_guard_hint": sorted(sem_protecao),
        "note": "routes_without_explicit_guard_hint é heurística (decorators na fonte); várias rotas são protegidas por middleware ou checagens internas.",
    }


def coletar_navegacao():
    from accounts.modulos import MODULOS_PORTAL

    def limpar(v):
        if callable(v):
            return f"<callable {getattr(v, '__qualname__', '?')}>"
        if isinstance(v, dict):
            return {k: limpar(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [limpar(x) for x in v]
        return v

    mods = [limpar(m) for m in sorted(MODULOS_PORTAL.values(), key=lambda m: (m["ordem"], m["slug"]))]
    return {"count": len(mods), "modules": mods}


RE_URL_EXTERNA = re.compile(r"https?://[\w\.\-]+(?:/[\w\-\./%{}]*)?")


def coletar_integracoes():
    env = sorted(
        set(re.findall(r"os\.environ(?:\.get)?\(?\[?\s*[\"']([A-Z0-9_]+)", ler(BASE / "config" / "settings.py")))
    )
    exemplo = BASE / ".env.example"
    env_exemplo = sorted(set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", ler(exemplo), re.M))) if exemplo.exists() else []
    hosts = defaultdict(set)
    clientes = defaultdict(set)
    for p in arquivos(BASE, ".py"):
        if "tests" in p.parts or p.name.startswith("test") or "migrations" in p.parts or "agent_lab" in p.parts:
            continue
        txt = ler(p)
        for u in RE_URL_EXTERNA.findall(txt):
            host = re.sub(r"^https?://", "", u).split("/")[0]
            if host not in {
                "localhost",
                "127.0.0.1",
                "www.w3.org",
                "schemas.openxmlformats.org",
                "purl.org",
                "schemas.microsoft.com",
            }:
                hosts[host].add(rel(p))
        for lib in ("requests", "urllib.request", "http.client", "httpx", "smtplib", "anthropic"):
            if re.search(rf"^\s*(import|from)\s+{re.escape(lib)}\b", txt, re.M):
                clientes[lib].add(rel(p))
    conhecidas = [
        {
            "name": "eProtocolo (PR)",
            "settings": "EPROTOCOLO",
            "default_mode": "mock",
            "code": ["core/leitura/eprotocolo.py", "viagens_oficios/protocolo_services.py"],
        },
        {"name": "OpenRouteService", "settings": "OPENROUTESERVICE_API_KEY", "default_mode": "desligado sem chave"},
        {
            "name": "OpenStreetMap/Nominatim (geocodificação)",
            "settings": "GEOCODIFICAR_SOB_DEMANDA",
            "default_mode": "ligado fora da suíte",
        },
        {"name": "WhatsApp Cloud API", "settings": "WHATSAPP_*", "default_mode": "desligado"},
        {
            "name": "Anthropic API (assistente)",
            "settings": "ANTHROPIC_API_KEY",
            "default_mode": "determinístico sem chave",
        },
        {"name": "SMTP", "settings": "EMAIL_HOST", "default_mode": "console"},
        {"name": "Banco legado GV (somente leitura)", "settings": "LEGADO_DB_*", "default_mode": "desligado"},
        {
            "name": "Word COM / LibreOffice / WeasyPrint (motores PDF)",
            "settings": "DOCUMENTOS_*",
            "default_mode": "auto",
        },
    ]
    return {
        "known": conhecidas,
        "env_vars_in_settings": env,
        "env_vars_in_env_example": env_exemplo,
        "outbound_hosts": {h: sorted(f) for h, f in sorted(hosts.items())},
        "http_clients": {k: sorted(v) for k, v in sorted(clientes.items())},
    }


def coletar_documentos():
    saida = {"types": [], "resources": [], "golden": []}
    try:
        from documentos.services.registry import default_document_registry

        for d in default_document_registry.all():
            saida["types"].append(
                {
                    "tipo": getattr(d.tipo, "value", str(d.tipo)),
                    "label": d.label,
                    "formats": [getattr(f, "value", str(f)) for f in d.formatos_permitidos],
                }
            )
    except Exception as exc:
        saida["types_error"] = repr(exc)
    try:
        from django.conf import settings as s

        saida["pdf_html_native"] = list(getattr(s, "DOCUMENTOS_PDF_HTML_NATIVO", ()))
    except Exception:
        pass
    for p in sorted((BASE / "documentos" / "resources").glob("*")):
        saida["resources"].append({"file": rel(p), "bytes": p.stat().st_size})
    for p in sorted((BASE / "documentos" / "tests" / "golden").rglob("*")):
        if p.is_file():
            saida["golden"].append(rel(p))
    saida["pdf_templates"] = sorted(t for t, _ in templates_projeto() if t.startswith("documentos/pdf"))
    return saida


# ---------------------------------------------------------------------------
# CSS: tokens, estilos, assets
# ---------------------------------------------------------------------------

RE_TOKEN_DEF = re.compile(r"(--[\w\-]+)\s*:\s*([^;}]+)")
RE_VAR_USO = re.compile(r"var\(\s*(--[\w\-]+)")
RE_HEX = re.compile(r"#(?:[0-9a-fA-F]{3,4}){1,2}\b")
RE_RGB = re.compile(r"rgba?\([^)]*\)")


def _css_files():
    return [p for p in arquivos(STATIC_DIR / "css", ".css")]


RE_VAR_SEM_FALLBACK = re.compile(r"var\(\s*(--[\w\-]+)\s*\)")
RE_DEF_DINAMICA = re.compile(r"(?:setProperty\(\s*[\"'`]|[\s;\"'{](?=--))(--[\w\-]+)\s*[\"'`]?\s*[:,]")


def coletar_tokens():
    defs = defaultdict(list)
    uso = Counter()
    sem_fallback = Counter()
    for p in _css_files():
        txt = ler(p)
        for nome, valor in RE_TOKEN_DEF.findall(txt):
            defs[nome].append({"file": rel(p), "value": valor.strip()})
    # Custom properties também nascem em style="--x: …" nos templates e via
    # element.style.setProperty("--x") no JS: contam como definição dinâmica.
    dinamicas = defaultdict(set)
    fontes_uso = list(_css_files()) + [p for _, p in templates_projeto()] + list(arquivos(STATIC_DIR / "js", ".js"))
    for p in fontes_uso:
        txt = ler(p)
        uso.update(RE_VAR_USO.findall(txt))
        sem_fallback.update(RE_VAR_SEM_FALLBACK.findall(txt))
        if p.suffix != ".css":
            for nome in RE_DEF_DINAMICA.findall(txt):
                dinamicas[nome].add(rel(p))
    tokens = []
    for nome in sorted(defs):
        valores = {d["value"] for d in defs[nome]}
        tokens.append(
            {
                "token": nome,
                "definitions": defs[nome],
                "conflicting_values": len(valores) > 1,
                "usages": uso.get(nome, 0),
                "category": _categoria_token(nome, defs[nome][0]["value"]),
            }
        )
    usados_nao_definidos = sorted(t for t in sem_fallback if t not in defs and t not in dinamicas)
    return {
        "count": len(tokens),
        "tokens": tokens,
        "unused_tokens": sorted(t["token"] for t in tokens if t["usages"] == 0),
        "dynamic_definitions": {k: sorted(v) for k, v in sorted(dinamicas.items())},
        "used_but_undefined": usados_nao_definidos,
        "note": "used_but_undefined = var(--x) SEM fallback, sem definição em CSS, template ou JS. Provável estilo quebrado.",
    }


def _categoria_token(nome, valor):
    if RE_HEX.search(valor) or "rgb" in valor or re.match(r"--(n|d|ok|wn|dg|in|nt)-", nome):
        return "color"
    if re.match(r"--s\d+|--pad|--gap|--esp", nome):
        return "spacing"
    if "radius" in nome or "raio" in nome:
        return "radius"
    if "shadow" in nome or "sombra" in nome:
        return "shadow"
    if nome.startswith("--f") or "font" in nome or "fonte" in nome:
        return "typography"
    if "motion" in nome or "transition" in nome or "dur" in nome:
        return "motion"
    if "z" == nome[2:3] or "z-" in nome:
        return "z-index"
    if valor.strip().endswith("px") or valor.strip().endswith("rem"):
        return "sizing"
    return "other"


def coletar_estilos():
    saida = []
    seletores = defaultdict(list)
    cores_hard = Counter()
    for p in _css_files():
        txt = ler(p)
        sem_coment = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
        regras = re.findall(r"([^{}]+)\{([^{}]*)\}", sem_coment)
        corpo_sem_tokens = "\n".join(c for _, c in regras if not c.strip().startswith("--"))
        hexes = RE_HEX.findall(re.sub(r"--[\w-]+\s*:[^;]+;", "", corpo_sem_tokens))
        cores_hard.update(h.lower() for h in hexes)
        for sel, _ in regras:
            for s in sel.split(","):
                s = s.strip()
                if (
                    s
                    and not s.startswith("@")
                    and not s.startswith("from")
                    and not s.startswith("to")
                    and not s.endswith("%")
                ):
                    seletores[s].append(rel(p))
        saida.append(
            {
                "file": rel(p),
                "lines": txt.count("\n") + 1,
                "bytes": p.stat().st_size,
                "rules": len(regras),
                "important": txt.count("!important"),
                "media_queries": sorted(set(re.findall(r"@media\s*([^{]+)", txt)))[:40],
                "hardcoded_colors": len(hexes) + len(RE_RGB.findall(corpo_sem_tokens)),
                "px_font_sizes": len(re.findall(r"font-size\s*:\s*\d+px", txt)),
                "outline_none": len(re.findall(r"outline\s*:\s*(none|0)\b", txt)),
            }
        )
    breakpoints = Counter()
    for p in _css_files():
        for media in re.findall(r"@media[^{]+", ler(p)):
            breakpoints.update(re.findall(r"(?:max|min)-width\s*:\s*(\d+)px", media))
    return {
        "files": saida,
        "breakpoints_px": dict(sorted(((k, v) for k, v in breakpoints.items()), key=lambda kv: int(kv[0]))),
        "hardcoded_color_frequency": dict(cores_hard.most_common(60)),
        "_selectors": seletores,
    }


def coletar_assets():
    saida = []
    for p in sorted(STATIC_DIR.rglob("*")):
        if p.is_file():
            partes = p.relative_to(STATIC_DIR).parts
            saida.append({"file": rel(p), "kind": partes[0], "vendor": "vendor" in partes, "bytes": p.stat().st_size})
    total = defaultdict(int)
    for a in saida:
        total[a["kind"]] += a["bytes"]
    return {"count": len(saida), "total_bytes_by_kind": dict(sorted(total.items())), "assets": saida}


def coletar_estados(todos):
    marcadores = {
        "empty": r"{%\s*empty\s*%}|estado-vazio|empty-state|Nenhum|Nenhuma",
        "loading": r"carregando|loading|aria-busy|spinner|skeleton",
        "error": r"form\.errors|non_field_errors|erro|alert--danger|aviso--erro|is-invalid|errorlist",
        "success": r"messages|sucesso|alert--ok|aviso--ok",
        "permission": r"perms\.|has_perm|pode_|somente_admin|is_superuser",
        "disabled": r"\bdisabled\b",
    }
    saida = []
    for t in todos:
        if not t["template"].startswith("pages/"):
            continue
        txt = ler(BASE / t["file"])
        saida.append({"template": t["template"], **{k: bool(re.search(v, txt, re.I)) for k, v in marcadores.items()}})
    faltando = {k: sorted(s["template"] for s in saida if not s[k]) for k in ("empty", "error")}
    return {
        "pages": saida,
        "pages_missing": faltando,
        "note": "Detecção textual (heurística). Confirme em runtime com os cenários de seed.",
    }


def coletar_duplicacao(todos, estilos, tokens):
    por_hash = defaultdict(list)
    for t in todos:
        por_hash[t["sha1_normalized"]].append(t["template"])
    tpl_dup = [v for v in por_hash.values() if len(v) > 1]
    sel_dup = {s: sorted(set(f)) for s, f in estilos["_selectors"].items() if len(set(f)) > 1}
    val_dup = defaultdict(list)
    for tk in tokens["tokens"]:
        if tk["category"] == "color":
            val_dup[tk["definitions"][0]["value"].lower()].append(tk["token"])
    js_funcs = defaultdict(set)
    for p in arquivos(STATIC_DIR / "js", ".js"):
        for f in re.findall(r"function\s+(\w+)\s*\(", ler(p)):
            js_funcs[f].add(rel(p))
    return {
        "identical_templates": tpl_dup,
        "selectors_defined_in_multiple_css_files": dict(sorted(sel_dup.items())[:400]),
        "selectors_defined_in_multiple_css_files_total": len(sel_dup),
        "color_tokens_with_same_value": {k: v for k, v in sorted(val_dup.items()) if len(v) > 1},
        "tokens_with_conflicting_definitions": [t["token"] for t in tokens["tokens"] if t["conflicting_values"]],
        "js_functions_defined_in_multiple_files": {k: sorted(v) for k, v in sorted(js_funcs.items()) if len(v) > 1},
    }


# ---------------------------------------------------------------------------
# orquestração
# ---------------------------------------------------------------------------


def gerar(destino: Path, *, com_contagem=False) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    resultados = {}

    def salvar(nome, dados):
        (destino / f"{nome}.json").write_text(
            json.dumps(dados, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
        )
        resultados[nome] = dados

    def seguro(fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as exc:  # um coletor quebrado não derruba os outros
            return {"error": f"{type(exc).__name__}: {exc}"}

    rotas = seguro(coletar_rotas)
    salvar("routes", rotas)
    todos, paginas, componentes = coletar_templates(rotas if "routes" in rotas else {"routes": []})
    salvar("pages", paginas)
    salvar("components", seguro(coletar_componentes, componentes))
    tabelas, modais = coletar_tabelas_modais(todos)
    salvar("tables", tabelas)
    salvar(
        "modals",
        {
            "count": sum(1 for d in modais["dialogs"] if d["element"] == "div"),
            "dialogs": [d for d in modais["dialogs"] if d["element"] == "div"],
        },
    )
    salvar(
        "dialogs",
        {
            "count": sum(1 for d in modais["dialogs"] if d["element"] == "dialog"),
            "dialogs": [d for d in modais["dialogs"] if d["element"] == "dialog"],
        },
    )
    salvar("forms", seguro(coletar_forms))
    salvar("entities", seguro(coletar_entidades, com_contagem))
    salvar("navigation", seguro(coletar_navegacao))
    salvar("permissions", seguro(coletar_permissoes, rotas))
    salvar("integrations", seguro(coletar_integracoes))
    salvar("documents", seguro(coletar_documentos))
    tokens = seguro(coletar_tokens)
    salvar("tokens", tokens)
    estilos = coletar_estilos()
    salvar("styles", {k: v for k, v in estilos.items() if not k.startswith("_")})
    salvar("assets", seguro(coletar_assets))
    salvar("states", seguro(coletar_estados, todos))
    salvar("duplication-report", seguro(coletar_duplicacao, todos, estilos, tokens))
    resumo = {
        "routes": rotas.get("count"),
        "pages": paginas["count"],
        "layouts": len(paginas["layouts"]),
        "template_components": len(componentes),
        "tables": tabelas["count"],
        "dialogs": len(modais["dialogs"]),
        "forms": resultados["forms"].get("count"),
        "entities": resultados["entities"].get("count"),
        "tokens": tokens.get("count"),
        "css_files": len(estilos["files"]),
        "assets": resultados["assets"].get("count"),
    }
    (destino / "summary.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resumo
