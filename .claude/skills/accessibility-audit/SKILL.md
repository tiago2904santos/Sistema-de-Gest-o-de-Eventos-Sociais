---
name: accessibility-audit
description: Auditoria WCAG 2.2 AA automatizada + teclado.
---

# accessibility-audit

Auditoria WCAG 2.2 AA automatizada + teclado.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run test:a11y` (catraca por página) e `tests/a11y/keyboard.spec.ts`.
2. Para uma página: `audit-page.mjs` (axe + h1/landmarks + alvos).
3. Checar manualmente o que axe não pega: ordem de foco, foco visível, leitura de erros, diálogos.
4. Plugin Axe (Deque): skill `axe-accessibility:mcp-audit` se houver chave do Axe MCP.

## Saída

`reports/accessibility/*`. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Sem aumento de critical/serious; baseline apertado se melhorou. Registrar decisões/descobertas em `docs/agent/memory/`.
