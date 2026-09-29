# Ferramentas de qualidade

| Ferramenta | Comando | Portão no CI |
|---|---|---|
| Django check | `manage.py check` | sim |
| Migrações | `manage.py makemigrations --check --dry-run` | sim |
| Testes Django | `manage.py test --parallel` (PG e SQLite) | sim |
| Testes do laboratório | `manage.py test agent_lab` | sim |
| Lint Python (crítico) | `ruff check --select E9,F63,F7,F82 .` | sim |
| Lint Python (completo) | `ruff check .` (292 achados em 29/09) | relatório |
| Formatação | `ruff format` só em código novo (`agent_lab/`, `scripts/agent/`) | sim nesses caminhos |
| Tipos (testes) | `npm run typecheck` | sim |
| Tokens em dia | `python scripts/agent/build_tokens.py --check` | sim |
| Playwright | smoke, e2e, regression, a11y (catraca), responsive (catraca) | sim |
| Visual | `npm run test:visual` | relatório até haver baseline gerado no runner |
| Dependências Python | `pip-audit -r requirements.txt` | relatório |
| Dependências Node | `npm audit --omit=dev` | relatório |
| Segredos | gitleaks (ação no CI) | sim |
| Atualizações | Dependabot (pip, npm, actions) semanal | — |
