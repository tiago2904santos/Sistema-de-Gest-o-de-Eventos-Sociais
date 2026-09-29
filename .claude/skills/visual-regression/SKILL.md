---
name: visual-regression
description: Detectar e revisar mudanças visuais.
---

# visual-regression

Detectar e revisar mudanças visuais.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run test:visual`; diffs em `reports/testing/artifacts/**` (expected/actual/diff).
2. Antes/depois fora dos testes: `tests/tools/visual-compare.mjs`.
3. Classificar cada diff: intencional (atualizar baseline) ou regressão (corrigir).
4. Atualizar: `npm run test:visual:update` **só** para os casos intencionais revisados.

## Saída

diffs revisados. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Nenhum baseline atualizado sem olhar o diff. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`audit_visual`, `compare_screenshots`, `testing_run_visual_tests` — ver `docs/agent/mcp.md`.

## Exemplo

`audit_visual {key:'oficios-lista'}` com 0,4% de diff → revisar `diff.png`.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
