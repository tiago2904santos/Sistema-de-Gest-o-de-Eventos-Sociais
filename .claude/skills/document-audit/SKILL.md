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

## Ferramentas MCP (project-mcp)

`project_inspect_document`, `testing_run_django_tests` — ver `docs/agent/mcp.md`.

## Exemplo

`testing_run_django_tests {labels:['documentos.tests.test_golden_templates']}`.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
