---
name: api-audit
description: Auditar endpoints JSON existentes (ex.: `/api/oficios/`, buscas remotas de select).
---

# api-audit

Auditar endpoints JSON existentes (ex.: `/api/oficios/`, buscas remotas de select).

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Filtrar `routes.json` por padrões `api/`, `.json`, `buscar`.
2. Checar autenticação/módulo, método, paginação, erros, N+1.

## Saída

achados. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Todo endpoint com guarda e resposta de erro definida. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`api_discover_endpoints`, `api_check_contracts`, `project_inspect_route` — ver `docs/agent/mcp.md`.

## Exemplo

10 endpoints JSON internos descobertos no cenário normal.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
