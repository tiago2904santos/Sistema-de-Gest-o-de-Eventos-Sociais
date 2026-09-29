---
name: document-audit
description: Auditar geração de documentos (DOCX/PDF).
---

# document-audit

Auditar geração de documentos (DOCX/PDF).

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `manage.py documentos_check --json`; motores disponíveis.
2. Goldens: `manage.py test documentos.tests.test_golden_templates`.
3. Gerar no lab e abrir o PDF (skill pdf) para conferir layout; nunca mudar golden sem revisão.

## Saída

achados. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Goldens verdes; motor usado registrado. Registrar decisões/descobertas em `docs/agent/memory/`.
