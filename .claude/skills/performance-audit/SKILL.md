---
name: performance-audit
description: Medir desempenho de carregamento e de consultas.
---

# performance-audit

Medir desempenho de carregamento e de consultas.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run test:perf` → `reports/performance/summary.md` (TTFB, LCP, CLS, bytes, long tasks).
2. Cenário `large`/`very_large` para listas: `npm run agent:reset -- --scenario large`.
3. Consultas: `django.test.utils.CaptureQueriesContext` ou `assertNumQueries` nos testes da view.
4. Lighthouse opcional: `npx lighthouse <url> --preset=desktop`.

## Saída

métricas + achados PERFORMANCE. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Hipótese de gargalo confirmada por medida antes de otimizar. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`audit_performance`, `obs_get_slow_queries`, `db_explain`, `testing_run_perf_tests` — ver `docs/agent/mcp.md`.

## Exemplo

Server-Timing mostra 180 queries numa lista → N+1 em `obs_get_slow_queries`.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
