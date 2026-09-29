# agent:self-test — PASSOU

2026-09-29T18:50:32.782Z · project-mcp com 106 ferramentas

| # | Passo | Ferramentas | OK | ms | Detalhe |
|---|---|---|---|---|---|
| 1 | Descobrir uma página (rota → view → template → componentes) | `project_inspect_route` `project_inspect_page` | ✅ | 3994 | viagens_oficios.views.lista em viagens_oficios/views.py:150 → pages/viagens_oficios/lista.html com 7 componentes |
| 2 | Iniciar o laboratório (LAB, sem migração pendente) | `lab_start` | ✅ | 3159 | ambiente LAB, relógio 2026-09-15T10:00:01.135507-03:00 |
| 3 | Abrir a página com Playwright como viagensGestor | `browser_open_page` | ✅ | 1478 | sessão p1, h1=Ofícios |
| 4 | Capturar screenshot da página inteira | `browser_capture_full_page` | ✅ | 464 | reports/mcp/2026-09-29/184803-002-full_page/full.png (imagem inline: 1) |
| 5 | Consultar a árvore de acessibilidade | `browser_inspect_accessibility_tree` | ✅ | 113 | 166 linhas; contém heading "Ofícios" |
| 6 | Executar Axe (auditoria de acessibilidade com achados P0–P4) | `audit_accessibility` | ✅ | 5883 | 2 achados {"P2":2}; color-contrast presente (KP-03 confirmado) |
| 7 | Consultar o DOM | `browser_inspect_dom` | ✅ | 38 | 6864 nós, 968 interativos, 206 formulários |
| 8 | Teste de interação (fluxo com busca + trace) | `browser_run_page_flow` | ✅ | 2124 | 4 passos, trace reports/mcp/2026-09-29/184809-005-flow/trace.zip |
| 9 | Comparar screenshot com o baseline | `audit_visual` | ✅ | 3259 | diff 0.000% vs tests/visual/snapshots/visual/pages.spec.ts/oficios-lista.png (0 achado) |
| 10 | Consultar o inventário (resumo + uso de componente) | `inventory_get_ui_inventory` `inventory_get_component_usage` | ✅ | 1611 | 601 rotas, 201 páginas; page_header usado 6× |
| 11 | Consultar o design system (tokens + conhecimento) | `inventory_get_design_tokens` `knowledge_search_design_system` | ✅ | 1205 | 176 tokens de cor; 1º trecho: docs/design-system/forms.md:1 |
| 12 | Consultar a memória do projeto (problemas conhecidos) | `inventory_get_known_problems` `knowledge_search_known_problems` | ✅ | 1051 | 2 problemas P1; busca → docs/agent/memory/known-problems.md:1 |
| 13 | Executar testes (smoke Playwright + agent_lab) | `testing_run_django_tests` `testing_run_smoke_tests` | ✅ | 125123 | django: Ran 27 tests in 57.320s — OK (expected failures=1); smoke: 22 ok / 0 falhas |
| 14 | Gerar relatório (consolidar achados) | `report_generate_audit_report` | ✅ | 5 | 2 achados em reports/mcp/2026-09-29/185023-007-audit_report/report.md |
| 15 | Verificar Git | `git_status` `git_history` | ✅ | 51 | branch agent/bootstrap-lab; último: feat(agent): project-mcp (105 ferramentas), doctor, self-tes |
| 16 | Banco: ambiente + EXPLAIN somente leitura + recusa de escrita | `db_environment` `db_explain` | ✅ | 3578 | LAB; plano: 2 / 0 / 52 / SEARCH viagens_oficios_oficio USING COVERING IN; DELETE recusado |
| 17 | Observabilidade: requisições com nº de SQL e Server-Timing | `obs_get_requests` | ✅ | 18 | 5 registros; última: 22.9 ms, 5 consultas |
| 18 | Seleção de ferramenta + pipeline do orquestrador | `agent_select_tool` `agent_get_pipeline` | ✅ | 8 | melhor: @axe-core/playwright; audit-module com 5 fases |
| 19 | Contratos de API | `api_check_contracts` | ✅ | 5022 | 10 endpoints; quebras: 0 |
