---
name: interaction-audit
description: Auditar interações (menus, abas, selects aprimorados, arrastar, autosave) com teclado e mouse.
---

# interaction-audit

Auditar interações (menus, abas, selects aprimorados, arrastar, autosave) com teclado e mouse.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Listar JS da página (`pages.json → static`).
2. Exercitar com Playwright: clique, teclado (Tab/Enter/Esc/setas), foco após ação.
3. Registrar exceções (`signals.pageErrors`) e estados intermediários (loading, erro de rede com `page.route`).

## Saída

spec e2e cobrindo a interação. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Interação funciona só com teclado e sobrevive a falha de rede. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`browser_run_page_flow`, `browser_test_keyboard`, `browser_inspect_console` — ver `docs/agent/mcp.md`.

## Exemplo

Select pesquisável: Enter escolhe, Esc fecha, foco volta ao campo.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
