---
name: navigation-audit
description: Auditar navegação (portal, barra do módulo, trilha).
---

# navigation-audit

Auditar navegação (portal, barra do módulo, trilha).

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `ui-inventory/navigation.json`.
2. Contar itens por módulo; overflow por viewport; item ativo correto; atalhos de teclado.
3. Consultar `docs/design-system/navigation.md`.

## Saída

achados. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Nenhuma navegação causa rolagem horizontal. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`audit_navigation`, `inventory_get_ui_inventory` — ver `docs/agent/mcp.md`.

## Exemplo

Navegação de Viagens com 12 itens → P3 + overflow P2.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
