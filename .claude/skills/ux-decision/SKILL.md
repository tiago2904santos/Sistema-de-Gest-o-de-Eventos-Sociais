---
name: ux-decision
description: Registrar uma decisão de UX com evidência e alternativas.
---

# ux-decision

Registrar uma decisão de UX com evidência e alternativas.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Problema observado (evidência de `audit_page`/fluxo).
2. Alternativas (2–3), critério (tarefa do usuário, acessibilidade, consistência com arquétipo).
3. Decisão + como medir sucesso; skills de apoio: `design:design-critique`, `design:ux-copy`.
4. Registrar em `docs/agent/memory/decisions.md` (e em `docs/ux/` se for padrão).

## Saída

Entrada de decisão datada com evidência. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

Linha de lista clicável (UX-01): título vira link; ⋮ fica para ações secundárias.

## Se falhar

Sem evidência de problema → não decida por gosto; audite primeiro.

## Pronto quando

Decisão rastreável e verificável.
