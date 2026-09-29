---
name: design-system-audit
description: Auditar o Design System: tokens, escalas, duplicação entre CSS, contraste.
---

# design-system-audit

Auditar o Design System: tokens, escalas, duplicação entre CSS, contraste.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run agent:inventory` → `tokens.json`, `styles.json`, `duplication-report.json`.
2. `npm run agent:tokens` → `reports/design/contrast.md`.
3. Atualizar `docs/design-system/*` (seções Hoje/Avaliação/Regra v4).
4. Pode usar a skill `design:design-system` do plugin Design para a crítica.

## Saída

docs do DS atualizados. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Números citados batem com o inventário do dia. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`inventory_get_design_tokens`, `inventory_get_duplicate_components`, `knowledge_search_design_system` — ver `docs/agent/mcp.md`.

## Exemplo

115 font-sizes distintos; `--d-500` = `--d-600`.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
