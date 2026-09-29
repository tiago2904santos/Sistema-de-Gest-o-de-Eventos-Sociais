---
name: migration-planning
description: Planejar a migração de um módulo para a arquitetura/DS alvo.
---

# migration-planning

Planejar a migração de um módulo para a arquitetura/DS alvo.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Atualizar a linha do módulo em `docs/architecture/migration-matrix.md`.
2. Listar rotas, templates, JS, regras de negócio e testes de caracterização.
3. Definir critérios de paridade (`parity-testing.md`) e ordem de páginas.

## Saída

plano no doc do módulo. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Riscos e paridade definidos antes de codar. Registrar decisões/descobertas em `docs/agent/memory/`.
