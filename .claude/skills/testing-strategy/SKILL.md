---
name: testing-strategy
description: Definir/ajustar a estratégia de testes de um trabalho.
---

# testing-strategy

Definir/ajustar a estratégia de testes de um trabalho.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Ler `docs/testing/strategy.md`.
2. Escolher camadas proporcionais ao risco (dinheiro/documento → caracterização + golden).
3. Cenários de seed necessários.

## Saída

plano de testes. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Cada risco coberto por pelo menos um teste real. Registrar decisões/descobertas em `docs/agent/memory/`.
