---
name: responsive-audit
description: Auditar layout em todas as viewports.
---

# responsive-audit

Auditar layout em todas as viewports.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run test:responsive` → `reports/responsive/summary.md`.
2. Para overflow: `layout.json` indica o seletor culpado; confirmar na captura.
3. Viewports em `tests/support/viewports.ts`.

## Saída

achados RESPONSIVE. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Nenhum overflow novo; culpado identificado por seletor. Registrar decisões/descobertas em `docs/agent/memory/`.
