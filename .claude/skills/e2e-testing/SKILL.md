---
name: e2e-testing
description: Escrever/rodar testes de ponta a ponta com Playwright.
---

# e2e-testing

Escrever/rodar testes de ponta a ponta com Playwright.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Usar `test`/`asRole` de `tests/support/lab.ts`; papéis em `roles.ts`; seed conhecido.
2. Seletores por papel/rótulo (`getByRole`, `getByLabel`), nunca coordenadas.
3. Cobrir sucesso, erro de validação, sem permissão, falha de rede.
4. `npm run test:e2e`.

## Saída

specs em `tests/e2e/`. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Teste estável em 3 execuções seguidas. Registrar decisões/descobertas em `docs/agent/memory/`.
