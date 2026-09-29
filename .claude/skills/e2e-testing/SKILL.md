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

## Ferramentas MCP (project-mcp)

`testing_run_e2e_tests`, `browser_run_page_flow` — ver `docs/agent/mcp.md`.

## Exemplo

`tests/e2e/permissions.spec.ts` como modelo de papel × acesso.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
