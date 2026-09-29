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
