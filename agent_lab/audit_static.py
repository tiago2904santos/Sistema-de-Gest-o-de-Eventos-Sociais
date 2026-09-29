"""Motor de auditoria — camada estática (código, templates, CSS, rotas).

Produz achados no formato comum (``docs/agent/audit-finding.schema.json``),
o mesmo que a camada de runtime (Playwright: axe, console, overflow, desempenho)
grava. Assim, qualquer auditoria — página, componente, fluxo ou módulo — termina
numa lista única de achados com severidade, categoria, evidência e recomendação.

Severidade:
    P0 sistema quebrado · P1 crítico · P2 importante · P3 melhoria relevante · P4 refinamento
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from django.conf import settings

from . import inventory as inv
from .depgraph import ciclos, imports_entre_apps

BASE = Path(settings.BASE_DIR)
CATEGORIAS = ("FUNCTIONAL", "UX", "VISUAL", "ACCESSIBILITY", "RESPONSIVE", "PERFORMANCE",
              "SECURITY", "ARCHITECTURE", "CONSISTENCY", "MAINTAINABILITY")
SEVERIDADES = ("P0", "P1", "P2", "P3", "P4")


def achado(regra, categoria, severidade, titulo, *, alvo, detalhe="", evidencia=None, recomendacao=""):
    assert categoria in CATEGORIAS and severidade in SEVERIDADES
    ident = hashlib.sha1(f"{regra}|{alvo.get('ref')}|{titulo}".encode()).hexdigest()[:12]
    return {
        "id": f"static-{ident}", "rule": regra, "source": "static", "category": categoria, "severity": severidade,
        "title": titulo, "detail": detalhe, "target": alvo, "evidence": evidencia or [], "recommendation": recomendacao,
    }


def _alvo_arquivo(caminho, tipo="module"):
    return {"type": tipo, "ref": caminho}


def regras_css(estilos, tokens):
    out = []
    for f in estilos["files"]:
        if f["outline_none"]:
            out.append(achado("css-outline-none", "ACCESSIBILITY", "P2", "Foco do teclado removido (outline: none)",
                              alvo=_alvo_arquivo(f["file"], "component"), detalhe=f"{f['outline_none']} ocorrência(s)",
                              evidencia=[{"kind": "file", "path": f["file"]}],
                              recomendacao="Use :focus-visible com anel visível baseado em token (ex.: outline: 2px solid var(--foco-anel))."))
        if f["hardcoded_colors"] > 10:
            out.append(achado("css-hardcoded-colors", "CONSISTENCY", "P3", "Cores fixas fora dos tokens",
                              alvo=_alvo_arquivo(f["file"], "component"), detalhe=f"{f['hardcoded_colors']} valores de cor literais",
                              evidencia=[{"kind": "file", "path": f["file"]}], recomendacao="Troque por var(--token); crie o token se faltar."))
        if f["important"] > 20:
            out.append(achado("css-important", "MAINTAINABILITY", "P3", "Uso intenso de !important",
                              alvo=_alvo_arquivo(f["file"], "component"), detalhe=f"{f['important']} ocorrências",
                              evidencia=[{"kind": "file", "path": f["file"]}], recomendacao="Resolva a especificidade na origem (camadas @layer)."))
    for t in tokens.get("used_but_undefined", []):
        out.append(achado("token-undefined", "VISUAL", "P2", f"Token usado sem definição: {t}", alvo={"type": "component", "ref": t},
                          recomendacao="Defina o token em :root ou corrija o nome; var() sem fallback vira valor inválido."))
    conflitos = [t for t in tokens.get("tokens", []) if t["conflicting_values"]]
    if conflitos:
        out.append(achado("token-conflict", "CONSISTENCY", "P3", "Tokens com valores diferentes em arquivos diferentes",
                          alvo={"type": "module", "ref": "static/css"}, detalhe=", ".join(t["token"] for t in conflitos[:30]),
                          recomendacao="Uma definição por token; variações viram tokens novos ou temas."))
    return out


def regras_templates(todos):
    out = []
    for t in todos:
        caminho = BASE / t["file"]
        txt = inv.ler(caminho)
        ref = {"type": "page" if t["template"].startswith("pages/") else "component", "ref": t["template"]}
        for m in re.finditer(r"<img\b(?![^>]*\balt=)[^>]*>", txt):
            out.append(achado("img-sem-alt", "ACCESSIBILITY", "P2", "Imagem sem atributo alt", alvo=ref,
                              evidencia=[{"kind": "snippet", "path": t["file"], "value": m.group(0)[:160]}],
                              recomendacao='alt="" para decorativa; texto descritivo para informativa.'))
        n_th = len(re.findall(r"<th\b", txt))
        if n_th and 'scope="' not in txt and "<thead" not in txt:
            out.append(achado("tabela-sem-scope", "ACCESSIBILITY", "P3", "Tabela sem thead/scope nos cabeçalhos", alvo=ref,
                              recomendacao='Use <thead> e scope="col"/"row" nos <th>.'))
        for m in re.finditer(r"<button\b[^>]*>\s*{%\s*include\s+\"components/icon\.html\"[^%]*%}\s*</button>", txt):
            if "aria-label" not in m.group(0) and "title=" not in m.group(0):
                out.append(achado("botao-icone-sem-nome", "ACCESSIBILITY", "P2", "Botão só com ícone e sem nome acessível", alvo=ref,
                                  evidencia=[{"kind": "snippet", "path": t["file"], "value": m.group(0)[:160]}],
                                  recomendacao="Acrescente aria-label descrevendo a ação."))
        safe = len(re.findall(r"\|\s*safe\b", txt))
        if safe:
            out.append(achado("template-safe", "SECURITY", "P3", "Uso de |safe (revisar origem do HTML)", alvo=ref, detalhe=f"{safe} ocorrência(s)",
                              recomendacao="Garanta que o conteúdo marcado como seguro é gerado pelo sistema, nunca por usuário."))
        if t["lines"] > 600:
            out.append(achado("template-grande", "MAINTAINABILITY", "P3", f"Template com {t['lines']} linhas", alvo=ref,
                              recomendacao="Quebre em componentes/partials ({% partialdef %} do Django 6)."))
        if t["inline_style_attrs"] > 15:
            out.append(achado("estilo-inline", "CONSISTENCY", "P4", f"{t['inline_style_attrs']} atributos style= inline", alvo=ref,
                              recomendacao="Mova para classes do design system."))
    return out


def regras_codigo(rotas, permissoes):
    out = []
    for p in inv.arquivos(BASE, ".py"):
        partes = p.relative_to(BASE).parts
        if "migrations" in partes or "agent_lab" in partes or "tests" in partes or p.name.startswith("test"):
            continue
        txt = inv.ler(p)
        linhas = txt.count("\n") + 1
        r = inv.rel(p)
        if "csrf_exempt" in txt:
            out.append(achado("csrf-exempt", "SECURITY", "P2", "View isenta de CSRF (revisar)", alvo=_alvo_arquivo(r),
                              detalhe="Aceitável só para webhooks com verificação de assinatura.",
                              recomendacao="Confirme verificação de assinatura/segredo e limite de taxa."))
        if re.search(r"\bmark_safe\(", txt):
            out.append(achado("mark-safe", "SECURITY", "P3", "mark_safe no código (revisar escapes)", alvo=_alvo_arquivo(r),
                              recomendacao="Prefira format_html/format_html_join."))
        if linhas > 1500 and ("views" in p.name or "services" in p.name or p.name == "models.py"):
            out.append(achado("modulo-grande", "MAINTAINABILITY", "P3", f"{p.name} com {linhas} linhas", alvo=_alvo_arquivo(r),
                              recomendacao="Divida por caso de uso (pacote views/ ou services/)."))
    for js in inv.arquivos(BASE / "static" / "js", ".js"):
        n = inv.ler(js).count("\n") + 1
        if n > 1000:
            out.append(achado("js-grande", "MAINTAINABILITY", "P3", f"JS com {n} linhas", alvo=_alvo_arquivo(inv.rel(js), "component"),
                              recomendacao="Módulos ES por responsabilidade; testes de unidade para a lógica."))
    s = inv.ler(BASE / "config" / "settings.py")
    if re.search(r'DJANGO_DEBUG",\s*"1"', s):
        out.append(achado("debug-padrao-ligado", "SECURITY", "P2", "DEBUG ligado quando a variável não existe",
                          alvo=_alvo_arquivo("config/settings.py"),
                          detalhe='DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1": um servidor sem .env sobe em modo debug.',
                          recomendacao="Padrão seguro: DEBUG desligado; desenvolvimento liga explicitamente no .env."))
    for rota in permissoes.get("routes_without_explicit_guard_hint", []):
        if rota.startswith("agent_lab:"):
            continue
        out.append(achado("rota-sem-guarda-explicita", "SECURITY", "P4", f"Rota sem guarda explícita na view: {rota}",
                          alvo={"type": "page", "ref": rota}, detalhe="Heurística: pode estar protegida por middleware ou checagem interna.",
                          recomendacao="Confirme com teste de acesso anônimo e de usuário sem módulo."))
    imp, _, _ = imports_entre_apps()
    for ciclo in ciclos(imp):
        out.append(achado("ciclo-imports", "ARCHITECTURE", "P3", f"Ciclo de dependência entre apps: {' ↔ '.join(ciclo)}",
                          alvo={"type": "module", "ref": ",".join(ciclo)},
                          recomendacao="Extraia o contrato comum para um app de base ou inverta a dependência via serviço/sinal."))
    return out


def regras_duplicacao(dup):
    out = []
    for grupo in dup.get("identical_templates", []):
        out.append(achado("template-identico", "MAINTAINABILITY", "P3", "Templates idênticos", alvo={"type": "component", "ref": grupo[0]},
                          evidencia=[{"kind": "file", "path": g} for g in grupo], recomendacao="Mantenha um e inclua."))
    total = dup.get("selectors_defined_in_multiple_css_files_total", 0)
    if total:
        out.append(achado("seletor-duplicado", "CONSISTENCY", "P3", f"{total} seletores definidos em mais de um CSS",
                          alvo={"type": "module", "ref": "static/css"}, recomendacao="Um dono por componente; o bridge deve encolher até sumir."))
    return out


def executar(destino: Path) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    rotas = inv.coletar_rotas()
    todos, _paginas, _comp = inv.coletar_templates(rotas)
    tokens = inv.coletar_tokens()
    estilos = inv.coletar_estilos()
    dup = inv.coletar_duplicacao(todos, estilos, tokens)
    permissoes = inv.coletar_permissoes(rotas)
    achados = regras_css(estilos, tokens) + regras_templates(todos) + regras_codigo(rotas, permissoes) + regras_duplicacao(dup)
    achados.sort(key=lambda a: (a["severity"], a["category"], a["target"]["ref"]))
    resumo = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total": len(achados),
        "by_severity": dict(sorted(Counter(a["severity"] for a in achados).items())),
        "by_category": dict(sorted(Counter(a["category"] for a in achados).items())),
    }
    (destino / "static-findings.json").write_text(json.dumps({"summary": resumo, "findings": achados}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = [f"# Auditoria estática — {resumo['total']} achados", "", f"Gerado em {resumo['generated_at']}.", "",
          "| Severidade | Qtde |", "|---|---|"] + [f"| {k} | {v} |" for k, v in resumo["by_severity"].items()]
    md += ["", "| Categoria | Qtde |", "|---|---|"] + [f"| {k} | {v} |" for k, v in resumo["by_category"].items()]
    md += ["", "## P0–P2", ""]
    for a in achados:
        if a["severity"] in ("P0", "P1", "P2"):
            md.append(f"- **{a['severity']} · {a['category']}** — {a['title']} (`{a['target']['ref']}`) {a['detail']}")
    (destino / "static-findings.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return resumo
