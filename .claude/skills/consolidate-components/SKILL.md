---
name: consolidate-components
description: Unificar componentes/estilos duplicados.
---

# consolidate-components

Unificar componentes/estilos duplicados.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `duplication-report.json` + `components.json` (sem uso, quase iguais).
2. Escolher o canônico, migrar usos, remover o resto.
3. Visual das páginas afetadas antes/depois.

## Saída

remoção de duplicatas. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Inventário mostra menos duplicação; nenhuma regressão visual. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`inventory_get_duplicate_components`, `inventory_get_component_usage` — ver `docs/agent/mcp.md`.

## Exemplo

308 seletores duplicados entre design-system.css, ds-v32.css e bridge.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
