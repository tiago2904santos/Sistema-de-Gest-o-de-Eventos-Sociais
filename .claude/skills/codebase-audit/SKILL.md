---
name: codebase-audit
description: Auditar a qualidade do código (tamanho, duplicação, lint, segurança, testes) de um app ou do projeto.
---

# codebase-audit

Auditar a qualidade do código (tamanho, duplicação, lint, segurança, testes) de um app ou do projeto.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `npm run agent:audit` e `.venv/bin/ruff check <caminho>`.
2. `ui-inventory/duplication-report.json` para duplicações de JS/CSS/templates.
3. Rodar os testes do app: `manage.py test <app> --parallel 4`.
4. Ler os maiores módulos (`static-findings` regra `modulo-grande`) e mapear responsabilidades.
5. Consolidar achados com severidade e recomendação concreta.

## Saída

achados em `reports/audit/`. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Nenhum achado sem evidência; P0/P1 reproduzidos. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`audit_static`, `inventory_get_duplicate_components`, `testing_run_django_tests` — ver `docs/agent/mcp.md`.

## Exemplo

`viagens_prestacoes/views.py` > 1.500 linhas → MAINTAINABILITY P3 com proposta de divisão por caso de uso.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
