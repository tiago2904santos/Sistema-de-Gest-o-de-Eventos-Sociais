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

## Ferramentas MCP (project-mcp)

`project_inspect_permission`, `project_inspect_route`, `inventory_get_ui_inventory`, `knowledge_search_business_rules`, `browser_run_page_flow` — ver `docs/agent/mcp.md`.

## Exemplo

Módulo Viagens: 12 itens de navegação, papéis gestor/operador/leitor, prestação criada por signal do ofício.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
