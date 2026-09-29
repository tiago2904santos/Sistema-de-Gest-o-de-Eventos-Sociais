# MCP

## Servidores configurados (`.mcp.json`)

| Servidor | O que é | Estado |
|---|---|---|
| **project-mcp** | MCP próprio (TypeScript, stdio): `npx tsx tools/project-mcp/src/server.ts` | READY — 106 ferramentas, provado por `npm run mcp:sanity` e `npm run agent:self-test` (19/19) |
| playwright | `@playwright/mcp` (Microsoft), exploração genérica | Para o Claude Code CLI na máquina do usuário; redundante com `browser_*` |

Plugins do claude.ai que trazem MCP (github, playwright, context7, figma, axe) **não sobem servidores nesta sessão
Cowork na nuvem** (diretórios sincronizados vazios; conferido com `RefreshMcpTools`). No Claude Code CLI, ou conectando
os conectores no claude.ai, eles funcionam — ver `manual-connections.md`.

## Decisão: um servidor, namespaces por prefixo

A missão sugeria `central-viagens-mcp`, `browser-evidence-mcp` e `project-knowledge-mcp`. Foram **consolidados** num só
(`project-mcp`) porque compartilham estado (servidor do lab, sessões autenticadas do navegador, pasta de evidências) e
porque um processo é mais simples de operar, testar e registrar. Nomes de ferramenta usam prefixo (`browser_open_page`)
em vez de ponto: clientes MCP exigem `^[a-zA-Z0-9_-]+$`.

| Namespace | Qtde | Ferramentas | Faz trabalho real via |
|---|---|---|---|
| `project_` | 9 | inspect_project, inspect_route, inspect_page, inspect_component, inspect_form, inspect_model, inspect_permission, inspect_integration, inspect_document | `manage.py agent_query` (introspecção Django, com fonte) |
| `inventory_` | 10 | get_ui_inventory, refresh, get_component_usage, get_duplicate_components, get_dependency_graph, get_page_archetypes, get_known_problems, get_design_tokens, get_migration_status, get_specimens | `ui-inventory/*.json`, docs, UI Lab |
| `lab_` | 6 | status, start, list_scenarios, reset, seed, create_test_scenario | `scripts/agent/lab.py`, `agent_seed/agent_reset` |
| `testing_` | 9 | run_{smoke,e2e,regression,a11y,visual,responsive,perf}_tests, run_django_tests, run_full_validation | Playwright (reporter JSON), Django test runner |
| `browser_` | 22 | open_page, navigate, click, fill, select, submit, inspect_{dom,accessibility_tree,landmarks,focus,console,network,layout}, capture_{screenshot,full_page,element}, test_viewport, test_keyboard, run_page_flow, get_trace, close, list_sessions | Playwright com sessões por papel e relógio ancorado |
| `audit_` + `compare_` | 12 | audit_{page,accessibility,responsive,performance,visual,component,form,table,modal,navigation,static}, compare_screenshots | axe, varredura de layout, vitals, pixelmatch, auditoria estática |
| `knowledge_` | 12 | search, search_{architecture,business_rules,design_system,ux_decisions,known_problems,migration_plan,product_docs,test_strategy,integrations,security_rules}, read_section | índice BM25 (radical de 5 letras) em docs, memória, skills, agentes e docstrings de regras |
| `git_` | 4 | status, diff, history, create_checkpoint | git (nada destrutivo) |
| `report_` | 5 | generate_{audit,regression,health,page}_report, command_center | consolidação de achados/relatórios |
| `db_` | 6 | environment, explain, validate_migrations, find_anomalies, index_review, audit | `agent_db`, `agent_env`, `agent_db_audit` (respeita LAB/DEV/STAGING/PRODUCTION) |
| `api_` | 2 | discover_endpoints, check_contracts | `agent_api` (rede externa bloqueada durante a varredura) |
| `obs_` | 4 | get_requests, get_slow_queries, get_errors, clear | `.lab/observability/*.jsonl` |
| `agent_` | 5 | list_skills, list_agents, get_pipeline, select_tool, doctor | `.claude/`, `docs/agent/pipelines`, `tool-registry.json`, `doctor.py` |

### Correspondência com os nomes pedidos na missão

`capture_page` → `browser_capture_full_page` · `capture_component` → `audit_component`/`browser_capture_element` ·
`get_visual_diff`/`compare_with_baseline` → `audit_visual` · `get_a11y_report` → `audit_accessibility` ·
`get_console_report` → `browser_inspect_console` · `get_network_report` → `browser_inspect_network` ·
`get_trace` → `browser_get_trace` · `inspect_layout` → `browser_inspect_layout` · `create_checkpoint` → `git_create_checkpoint` ·
`generate_health_report` → `report_generate_health_report`. Nenhuma ferramenta é simulada: todas executam e devolvem fonte/evidência.

## Padrão de resposta

JSON legível; capturas também como imagem inline (< 1,5 MB). Auditorias devolvem `findings[]` no formato
`audit-finding.schema.json` com **finding/title, severity, source, evidence, recommendation, verification**, e gravam
`findings.json` em `reports/mcp/<data>/<hora>-<n>-<ferramenta>/`. Erros viram `isError` estruturado (o servidor não cai).

## Segurança

Ações que escrevem dados (`audit_form`, `browser_submit`, `lab_*`) exigem que o servidor esteja em **LAB** (marca
interna no banco). `db_explain` só aceita SELECT/WITH em transação somente-leitura. `git_create_checkpoint` só cria tag.

## Como testar

```bash
npm run mcp:sanity        # handshake + 2 chamadas reais (CI)
npm run agent:self-test   # 19 passos ponta a ponta → reports/agent/self-test.md
```
