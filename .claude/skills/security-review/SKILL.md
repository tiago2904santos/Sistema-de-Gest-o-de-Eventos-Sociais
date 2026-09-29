---
name: security-review
description: Revisão de segurança de uma mudança (diff) — diferente de security-audit, que audita a aplicação toda.
---

# security-review

Revisão de segurança de uma mudança (diff) — diferente de security-audit, que audita a aplicação toda.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. `git_diff` da mudança.
2. Checklist: autenticação/módulo nas views novas (`acesso_ao_modulo`), CSRF, `|safe`/`mark_safe`, uploads privados, segredos, SQL cru, permissões por papel.
3. `npm run agent:security` (bandit + check --deploy) e `audit_static` filtrando SECURITY.
4. Teste de acesso anônimo e `lab.sem_modulo` nas rotas novas.
5. Revisão profunda opcional: comando `/code-review` (plugin code-review).

## Saída

Achados SECURITY com severidade. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

View nova sem `@acesso_ao_modulo` → P1 com teste de acesso.

## Se falhar

Ferramenta indisponível → checklist manual, sem pular itens.

## Pronto quando

Nenhum P0–P2 aberto na mudança.
