---
name: architecture-audit
description: Auditar a arquitetura do sistema (camadas, acoplamento entre apps, ciclos, fronteiras) e propor evolução. Use ao avaliar mudanças estruturais ou antes de ADRs.
---

# architecture-audit

Auditar a arquitetura do sistema (camadas, acoplamento entre apps, ciclos, fronteiras) e propor evolução. Use ao avaliar mudanças estruturais ou antes de ADRs.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run agent:depgraph` → ler `reports/architecture/dependency-graph.json` (ciclos, fan-in/out, instabilidade).
2. Ler `docs/architecture/current-architecture.md` e ADRs vigentes em `docs/architecture/adr/`.
3. Para cada app: responsabilidades (models/services/views), dependências de domínio em `core`, regras no banco.
4. Classificar achados (ARCHITECTURE/MAINTAINABILITY, P0–P4) no formato de `docs/agent/audit-finding.schema.json`.
5. Propor mudanças com custo/risco; decisões grandes viram ADR novo.

## Saída

`reports/architecture/*`, achados, rascunho de ADR. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Todo ciclo e toda fronteira violada citados com evidência (arquivo/aresta). Registrar decisões/descobertas em `docs/agent/memory/`.
