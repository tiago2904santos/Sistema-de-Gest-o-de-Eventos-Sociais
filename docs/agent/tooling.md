# Ferramentas — mapa rápido

Registro completo e classificado: [`tool-registry.json`](tool-registry.json). Inventário comentado: [`tooling-inventory.md`](tooling-inventory.md).
Política de escolha: [`tool-selection-policy.md`](tool-selection-policy.md). Versões: [`compatibility.md`](compatibility.md).

| Preciso de… | Use |
|---|---|
| Entender uma rota/página/modelo | `project_inspect_*` (ou `manage.py agent_query …`) |
| Ver a tela como um papel | `browser_open_page` → `browser_*` |
| Auditar | `audit_page` (tudo) ou `audit_{accessibility,responsive,performance,visual,form,table,modal,navigation,component,static}` |
| Testar | `testing_run_*` ou `npm run test:*`; validação completa: `testing_run_full_validation` |
| Estado previsível | `lab_reset {scenario}` / `lab_create_test_scenario` |
| Banco | `db_environment`, `db_explain`, `db_validate_migrations`, `db_find_anomalies`, `db_audit` |
| API | `api_discover_endpoints`, `api_check_contracts` |
| Lento? | `obs_get_slow_queries`, `audit_performance` |
| Saber algo documentado | `knowledge_search*` → `knowledge_read_section` |
| Saúde do agente | `npm run agent:doctor` (`--fix`), `npm run agent:health`, `npm run agent:self-test` |
| Segurança | `npm run agent:security` |
| Painel | `npm run agent:command-center` → `reports/agent/command-center.json` |
