#!/usr/bin/env python3
"""Compila tokens/*.json (formato W3C DTCG) em CSS e mede contraste.

    python scripts/agent/build_tokens.py          # gera static/css/tokens.css + reports/design/contrast.md
    python scripts/agent/build_tokens.py --check  # falha se tokens.css estiver desatualizado (CI)

O CSS gerado usa o prefixo ``--t-`` para conviver com os tokens atuais do
ds-v32.css sem colisão durante a migração. Ele ainda NÃO é carregado pelo
produto — a adoção é página a página (docs/architecture/adr/0001-arquitetura-alvo.md).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TOKENS = RAIZ / "tokens"
SAIDA = RAIZ / "static" / "css" / "tokens.css"
RELATORIO = RAIZ / "reports" / "design" / "contrast.md"


def achatar(no, caminho=(), herdado_tipo=None):
    tipo = no.get("$type", herdado_tipo) if isinstance(no, dict) else herdado_tipo
    if isinstance(no, dict) and "$value" in no:
        yield caminho, no["$value"], tipo, no.get("$extensions", {}).get("cv", {})
        return
    if isinstance(no, dict):
        for k, v in no.items():
            if not k.startswith("$"):
                yield from achatar(v, caminho + (k,), tipo)


def carregar():
    todos = {}
    for arq in sorted(TOKENS.glob("*.json")):
        for caminho, valor, tipo, ext in achatar(json.loads(arq.read_text(encoding="utf-8"))):
            todos[".".join(caminho)] = {"value": valor, "type": tipo, "ext": ext, "file": arq.name}
    return todos


def var(caminho):
    return "--t-" + caminho.replace(".", "-")


def css_valor(t, todos):
    v = t["value"]
    if isinstance(v, str):
        return re.sub(r"\{([\w\.\-]+)\}", lambda m: f"var({var(m.group(1))})", v)
    if t["type"] == "fontFamily":
        return ",".join(f'"{f}"' if " " in f else f for f in v)
    if t["type"] == "cubicBezier":
        return f"cubic-bezier({','.join(str(x) for x in v)})"
    return str(v)


def resolver(caminho, todos, prof=0):
    v = todos[caminho]["value"]
    m = re.fullmatch(r"\{([\w\.\-]+)\}", v) if isinstance(v, str) else None
    return resolver(m.group(1), todos, prof + 1) if m and prof < 10 else v


def luminancia(hexa):
    h = hexa.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    canais = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contraste(a, b):
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def gerar():
    todos = carregar()
    linhas = [
        "/* GERADO por scripts/agent/build_tokens.py a partir de tokens/*.json — não edite à mão. */",
        "/* Prefixo --t- para conviver com os tokens atuais durante a migração. */",
        ":root{",
    ]
    for caminho in sorted(todos):
        t = todos[caminho]
        if caminho.startswith("breakpoint."):
            continue  # custom properties não funcionam em @media; ficam documentados
        linhas.append(f"  {var(caminho)}:{css_valor(t, todos)};")
    linhas.append("}")
    return "\n".join(linhas) + "\n", todos


def relatorio_contraste(todos):
    fundos = {"papel": resolver("color.base.paper", todos), "branco": resolver("color.base.white", todos)}
    linhas = [
        "# Contraste dos tokens de cor (WCAG 2.x)",
        "",
        "Texto normal exige 4,5:1; texto grande (≥ 18,66px negrito ou 24px) e componentes de interface, 3:1.",
        "",
        "| Token | Cor | sobre papel | sobre branco | AA texto |",
        "|---|---|---|---|---|",
    ]
    for caminho in sorted(todos):
        if not caminho.startswith("color.") or ".bg" in caminho or ".border" in caminho:
            continue
        cor = resolver(caminho, todos)
        if not (isinstance(cor, str) and cor.startswith("#")):
            continue
        cp, cb = contraste(cor, fundos["papel"]), contraste(cor, fundos["branco"])
        linhas.append(
            f"| `{caminho}` | `{cor}` | {cp:.2f} | {cb:.2f} | {'✅' if min(cp, cb) >= 4.5 else ('⚠️ só grande/UI' if min(cp, cb) >= 3 else '❌')} |"
        )
    for nome in ("success", "warning", "danger", "info", "neutral"):
        t, b = resolver(f"color.status.{nome}.text", todos), resolver(f"color.status.{nome}.bg", todos)
        linhas.append(
            f"| `status.{nome}.text` sobre `status.{nome}.bg` | `{t}`/`{b}` | {contraste(t, b):.2f} | — | {'✅' if contraste(t, b) >= 4.5 else '❌'} |"
        )
    return "\n".join(linhas) + "\n"


def main():
    css, todos = gerar()
    if "--check" in sys.argv:
        atual = SAIDA.read_text(encoding="utf-8") if SAIDA.exists() else ""
        if atual != css:
            sys.exit("static/css/tokens.css desatualizado: rode python scripts/agent/build_tokens.py")
        print("tokens.css em dia")
        return
    SAIDA.write_text(css, encoding="utf-8")
    RELATORIO.parent.mkdir(parents=True, exist_ok=True)
    RELATORIO.write_text(relatorio_contraste(todos), encoding="utf-8")
    print(f"{len(todos)} tokens → {SAIDA.relative_to(RAIZ)}; contraste → {RELATORIO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
