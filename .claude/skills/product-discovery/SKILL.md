---
name: product-discovery
description: Entender um módulo/fluxo do produto: quem usa, objetivos, regras de negócio, estados e integrações.
---

# product-discovery

Entender um módulo/fluxo do produto: quem usa, objetivos, regras de negócio, estados e integrações.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Ler `docs/product/modules.md`, `docs/PLANO_MESTRE_UNIFICACAO.md` e docs da fase do módulo.
2. Mapear rotas (`routes.json` por namespace), formulários (`forms.json`), entidades e status (choices).
3. Percorrer o fluxo no lab como cada papel (`tests/support/roles.ts`) com o Playwright MCP ou `audit-page.mjs --click`.
4. Registrar regras implícitas descobertas em `docs/agent/memory/discoveries.md`.

## Saída

resumo do módulo em `docs/product/`. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Fluxo documentado com estados e papéis, validado navegando. Registrar decisões/descobertas em `docs/agent/memory/`.
