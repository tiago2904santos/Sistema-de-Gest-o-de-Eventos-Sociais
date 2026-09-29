---
name: ui-audit
description: Auditoria de interface ampla (várias páginas): visual, consistência, acessibilidade, responsivo.
---

# ui-audit

Auditoria de interface ampla (várias páginas): visual, consistência, acessibilidade, responsivo.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run agent:reset -- --scenario normal` e `npm run test:a11y test:responsive test:perf`.
2. Consolidar `reports/*/summary.md` e cruzar com `static-findings`.
3. Para as piores páginas, `page-audit`.
4. Agrupar problemas transversais (tokens, componentes) antes dos pontuais.

## Saída

relatório consolidado de UI. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Top problemas priorizados com evidência (captura/axe/overflow). Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`testing_run_a11y_tests`, `testing_run_responsive_tests`, `testing_run_perf_tests`, `report_generate_audit_report` — ver `docs/agent/mcp.md`.

## Exemplo

20 páginas × 6 viewports → 40 combinações com overflow, todas pela navegação de Viagens.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
