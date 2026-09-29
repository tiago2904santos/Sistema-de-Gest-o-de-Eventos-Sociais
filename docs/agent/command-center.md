# UI Command Center — base

Painel futuro de saúde do projeto. A infraestrutura de dados já existe; o painel lê só arquivos gerados:

| Bloco | Fonte |
|---|---|
| PROJECT HEALTH | `reports/agent/health.json` |
| Pages / Components | `ui-inventory/summary.json`, `pages.json`, `components.json` |
| Coverage (testes) | `reports/testing/playwright-results.json` + `manage.py test` |
| A11y | `reports/accessibility/*.json`, `tests/a11y/baseline.json` |
| Visual consistency | `ui-inventory/duplication-report.json`, `tokens.json` |
| Responsive | `reports/responsive/**`, `tests/responsive/baseline.json` |
| Performance | `reports/performance/*.json` |
| Security / Tech debt | `reports/audit/static-findings.json` (categorias SECURITY, MAINTAINABILITY, ARCHITECTURE) |
| UX debt | achados UX/VISUAL + `docs/agent/memory/known-problems.md` |
| TOP PROBLEMS | achados P0–P2 ordenados |
| RECENT CHANGES / REGRESSIONS | `git log` + diffs de baseline |
| PAGES NOT AUDITED | `ui-inventory/routes.json` − páginas com relatório em `reports/audit/` |
| DUPLICATED / LEGACY COMPONENTS | `duplication-report.json`, `components.json → unused_template_components`, uso de `design-system.css` |

Implementação sugerida: página do UI Lab (`/_lab/painel/`) lendo esses JSON, ou um Artifact publicado a partir deles.
