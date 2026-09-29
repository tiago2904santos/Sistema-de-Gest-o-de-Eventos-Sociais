---
name: browser-evidence
description: Obter evidência de navegador rastreável (capturas, DOM, árvore de acessibilidade, console, rede, trace) em vez de opinião.
---

# browser-evidence

Obter evidência de navegador rastreável (capturas, DOM, árvore de acessibilidade, console, rede, trace) em vez de opinião.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. `browser_open_page {path, role}` (sessão autenticada, relógio ancorado).
2. `browser_inspect_dom` / `browser_inspect_accessibility_tree` / `browser_inspect_landmarks` / `browser_inspect_layout`.
3. `browser_inspect_console` e `browser_inspect_network {filter:'failed'}`.
4. `browser_capture_full_page` / `browser_capture_element`.
5. Fluxos: `browser_run_page_flow` com `trace:true` (abre com `npx playwright show-trace`).

## Saída

Caminhos em `reports/mcp/<data>/…` citados na conclusão. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

"o botão Salvar não responde" → flow com click + `browser_inspect_console` mostra `TypeError` em app.js:120.

## Se falhar

Sessão expirou/login falhou → `lab_reset` e reabrir; servidor fora → `lab_start`.

## Pronto quando

Toda conclusão cita um arquivo de evidência.
