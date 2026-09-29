---
name: data-migration
description: Migrar dados com segurança.
---

# data-migration

Migrar dados com segurança.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Padrão estrutura → dados → estrutura; idempotente (`legado_origem/legado_pk`), reversível.
2. Testar pelo executor de migrações; ensaiar em cópia (`MEDIA_ROOT`/banco de carga).
3. Nunca em produção sem backup e autorização explícita.

## Saída

migrações + testes. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Ida e volta testadas. Registrar decisões/descobertas em `docs/agent/memory/`.
