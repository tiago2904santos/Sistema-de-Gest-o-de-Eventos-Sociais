# Navegador

| Uso | Ferramenta |
|---|---|
| Evidência reprodutível (auditoria, fluxo, captura) | `browser_*` / `audit_*` do project-mcp e Playwright (`tests/`) |
| Olhar a app local do usuário no painel do app | Claude Browser (built-in) |
| Chrome real do usuário | Claude in Chrome (só com pedido) |

Sessões do project-mcp: contexto por papel (`admin`, `viagensGestor`, …, `semModulo`, `anon`), login real com
`.lab/auth/<papel>.json` (refeito sozinho se o banco foi recriado), relógio fixo em 15/09/2026 10:00 −03, viewport nomeada.
Cada ação devolve URL/status/erros; capturas em `reports/mcp/…`. `browser_run_page_flow` grava trace (`npx playwright show-trace`).
Seletores: CSS, `role=button[name=Salvar]`, `label=Usuário`, `text=…` — nunca coordenadas.
