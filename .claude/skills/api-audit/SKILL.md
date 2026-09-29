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
