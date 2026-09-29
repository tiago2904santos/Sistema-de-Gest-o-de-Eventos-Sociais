---
name: api-design
description: Desenhar API (se/quando um cliente não-web exigir — ver gatilhos do ADR 0001).
---

# api-design

Desenhar API (se/quando um cliente não-web exigir — ver gatilhos do ADR 0001).

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Contrato primeiro (OpenAPI via django-ninja/DRF).
2. Reusar services existentes; permissões do módulo.
3. Testes de contrato.

## Saída

especificação + endpoints. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Contrato versionado e testado. Registrar decisões/descobertas em `docs/agent/memory/`.
