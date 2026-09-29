---
name: database-audit
description: Auditar o banco: relações, on_delete, constraints, índices, dados órfãos/duplicados e campos legados.
---

# database-audit

Auditar o banco: relações, on_delete, constraints, índices, dados órfãos/duplicados e campos legados.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run agent:db-audit` → `reports/data/db-audit.md`.
2. Para cada cascata sensível, reproduzir o efeito no lab dentro de `transaction.atomic()` revertida (ver KP-00).
3. Checar `ui-inventory/entities.json` (constraints, choices, unique).
4. Com banco real: só leitura, relatório fora do git, sem dados pessoais.

## Saída

`reports/data/*`, entradas em `known-problems.md`. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Cascatas confirmadas por teste; nada destrutivo fora do lab. Registrar decisões/descobertas em `docs/agent/memory/`.
