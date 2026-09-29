---
name: visual-regression
description: Detectar e revisar mudanças visuais.
---

# visual-regression

Detectar e revisar mudanças visuais.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run test:visual`; diffs em `reports/testing/artifacts/**` (expected/actual/diff).
2. Antes/depois fora dos testes: `tests/tools/visual-compare.mjs`.
3. Classificar cada diff: intencional (atualizar baseline) ou regressão (corrigir).
4. Atualizar: `npm run test:visual:update` **só** para os casos intencionais revisados.

## Saída

diffs revisados. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Nenhum baseline atualizado sem olhar o diff. Registrar decisões/descobertas em `docs/agent/memory/`.
