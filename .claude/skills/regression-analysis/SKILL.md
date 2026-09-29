---
name: regression-analysis
description: Investigar uma regressão.
---

# regression-analysis

Investigar uma regressão.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Reproduzir no lab com cenário fixo; teste que falha.
2. `git bisect run` com o teste.
3. Causa raiz + teste de regressão em `tests/regression` ou no app.

## Saída

commit culpado + teste. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Teste falha antes e passa depois da correção. Registrar decisões/descobertas em `docs/agent/memory/`.
