---
name: database-review
description: Revisar mudança de banco (migração, modelo, consulta) antes de aplicar.
---

# database-review

Revisar mudança de banco (migração, modelo, consulta) antes de aplicar.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. `db_validate_migrations` — pendentes, destrutivas, RunPython, conflitos.
2. `db_environment` — onde vai rodar? PRODUCTION é somente leitura para o agente.
3. Consultas novas: `db_explain` (ANALYZE só em LAB/DEV); N+1: `obs_get_slow_queries`.
4. Dados: `db_find_anomalies`; cascatas: `db_audit`.
5. Migração de dados: ida e volta testadas pelo executor (padrão da F1).

## Saída

Parecer com riscos e plano de rollback. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

`RemoveField` pendente em produção → exige backup + ensaio em cópia.

## Se falhar

Ambiente não é LAB/DEV → só leitura; não execute nada destrutivo.

## Pronto quando

Migração segura, reversível e medida.
