---
name: release-validation
description: Validar uma entrega antes de merge/deploy.
---

# release-validation

Validar uma entrega antes de merge/deploy.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run agent:health`.
2. `manage.py test --parallel` (PG) + `npm test`.
3. Migrações pendentes em produção? (lista em `showmigrations`).
4. Resumo com riscos e rollback.

## Saída

relatório de validação. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Tudo verde ou exceções justificadas. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`testing_run_full_validation`, `db_validate_migrations`, `report_generate_health_report` — ver `docs/agent/mcp.md`.

## Exemplo

Validação completa antes de merge (também cobre a 'release-readiness' da missão).

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
