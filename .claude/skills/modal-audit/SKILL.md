---
name: modal-audit
description: Auditar modais/diálogos.
---

# modal-audit

Auditar modais/diálogos.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `ui-inventory/dialogs.json`/`modals.json`.
2. Abrir por teclado; foco inicial; Esc; foco volta ao gatilho; nome acessível; rolagem interna.

## Saída

achados. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Checklist de `docs/design-system/dialogs.md` cumprido. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`audit_modal`, `browser_test_keyboard` — ver `docs/agent/mcp.md`.

## Exemplo

`audit_modal {path:'/viagens/oficios/', trigger:'[data-abrir-dialogo]'}`.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
