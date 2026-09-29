---
name: component-design
description: Criar ou redesenhar um componente do DS v4.
---

# component-design

Criar ou redesenhar um componente do DS v4.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Ler `docs/design-system/*` relevantes e tokens.
2. Implementar em `templates/components/v4/` com contrato comentado; CSS só com `--t-*`.
3. Adicionar espécimes (todos os estados) em `agent_lab/specimens.py`.
4. Visual + axe no espécime; documentar em `docs/design-system/`.

## Saída

componente + espécimes + doc. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Todos os estados no UI Lab, axe limpo, baseline criado. Registrar decisões/descobertas em `docs/agent/memory/`.
