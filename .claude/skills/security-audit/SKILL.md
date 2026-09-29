---
name: security-audit
description: Auditoria de segurança da aplicação.
---

# security-audit

Auditoria de segurança da aplicação.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `static-findings` (SECURITY), `permissions.json`, rotas públicas.
2. Testar acesso anônimo e `lab.sem_modulo` nas rotas do módulo.
3. Settings de produção (DEBUG, HSTS, cookies), uploads privados, tokens de link (hash, expiração).
4. `pip-audit`, `npm audit`; plugin finecomb/code-review para revisão profunda.

## Saída

achados SECURITY. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Nenhuma rota protegida acessível sem permissão. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`audit_static`, `project_inspect_permission`, `browser_open_page` — ver `docs/agent/mcp.md`.

## Exemplo

`lab.sem_modulo` em /viagens/oficios/ → 403 esperado.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
