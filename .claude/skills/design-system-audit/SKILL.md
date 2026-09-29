---
name: design-system-audit
description: Auditar o Design System: tokens, escalas, duplicação entre CSS, contraste.
---

# design-system-audit

Auditar o Design System: tokens, escalas, duplicação entre CSS, contraste.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run agent:inventory` → `tokens.json`, `styles.json`, `duplication-report.json`.
2. `npm run agent:tokens` → `reports/design/contrast.md`.
3. Atualizar `docs/design-system/*` (seções Hoje/Avaliação/Regra v4).
4. Pode usar a skill `design:design-system` do plugin Design para a crítica.

## Saída

docs do DS atualizados. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Números citados batem com o inventário do dia. Registrar decisões/descobertas em `docs/agent/memory/`.
