---
name: regression-analysis
description: Investigar uma regressão.
---

# regression-analysis

Investigar uma regressão.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Reproduzir no lab com cenário fixo; teste que falha.
2. `git bisect run` com o teste.
3. Causa raiz + teste de regressão em `tests/regression` ou no app.

## Saída

commit culpado + teste. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Teste falha antes e passa depois da correção. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`git_history`, `testing_run_regression_tests`, `report_generate_regression_report` — ver `docs/agent/mcp.md`.

## Exemplo

`git bisect run npx playwright test -g 'oficios'` (também cobre 'regression-investigation').

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
