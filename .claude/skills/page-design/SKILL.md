---
name: page-design
description: Redesenhar uma página seguindo um arquétipo.
---

# page-design

Redesenhar uma página seguindo um arquétipo.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Escolher arquétipo (`page-archetypes.md`).
2. Ciclo `docs/agent/design-review-loop.md` completo (antes/depois).
3. Só componentes do DS; estados completos.

## Saída

página + evidência antes/depois. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Catracas iguais ou melhores; paridade de dados. Registrar decisões/descobertas em `docs/agent/memory/`.
