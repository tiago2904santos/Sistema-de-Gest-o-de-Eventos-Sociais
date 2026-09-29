---
name: refactor-component
description: Refatorar componente existente sem mudar comportamento.
---

# refactor-component

Refatorar componente existente sem mudar comportamento.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Espécimes e baseline antes.
2. Refatorar; rodar visual (diff zero ou intencional) e testes das páginas que usam (`used_by`).
3. Commit com evidência.

## Saída

refatoração. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Diff visual zero nas páginas consumidoras. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`inventory_get_component_usage`, `audit_component`, `testing_run_visual_tests` — ver `docs/agent/mcp.md`.

## Exemplo

Consolidar `lista_registros` sem diff visual nas 11 páginas que o usam.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
