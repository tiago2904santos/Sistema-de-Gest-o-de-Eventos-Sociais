---
name: component-audit
description: Auditar um componente de template em todos os estados.
---

# component-audit

Auditar um componente de template em todos os estados.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Localizar em `ui-inventory/components.json` (uso, onde é incluído).
2. Garantir espécimes em `agent_lab/specimens.py` para default/focus/error/disabled/empty/long-content.
3. Abrir `/_lab/c/<id>/`; `npm run test:visual`; axe no espécime (`runAxe` com `include: '#alvo'`).
4. Comparar o contrato comentado do template com o uso real (parâmetros não documentados).

## Saída

espécimes + achados. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Todos os estados renderizam; sem violação axe crítica. Registrar decisões/descobertas em `docs/agent/memory/`.
