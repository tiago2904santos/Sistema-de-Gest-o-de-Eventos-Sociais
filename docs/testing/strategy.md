# Estratégia de testes

| Camada | Ferramenta | Onde | Quando rodar |
|---|---|---|---|
| Unidade/integração de domínio | Django `TestCase` (3.054) | `*/tests*.py` | sempre |
| Caracterização (dinheiro, numeração) | Django | `viagens_roteiros`, `viagens_oficios`… | antes de mexer em regra |
| Goldens de documento | Django + arquivos | `documentos/tests/golden` | mudança em documento |
| Laboratório | Django | `agent_lab/tests.py` | sempre |
| Smoke | Playwright | `tests/smoke` (sonda, login, 20 páginas-chave, varredura de todas as rotas GET) | todo commit |
| E2E | Playwright | `tests/e2e` (login/logout, troca de senha, permissões, busca, falha de rede) | todo commit |
| Regressão | Playwright | `tests/regression` (bugs corrigidos + `test.fail` dos abertos) | todo commit |
| Acessibilidade | Playwright + axe | `tests/a11y` (catraca por página + teclado) | todo commit |
| Visual | Playwright | `tests/visual/specs` (espécimes do UI Lab + páginas inteiras) | mudança de UI |
| Responsivo | Playwright | `tests/responsive` (6 viewports × 20 páginas, catraca de overflow) | mudança de UI |
| Desempenho | Playwright | `tests/perf` (LCP, CLS, bytes, requisições) | mudança de UI/consulta |

Princípios: comportamento real acima de cobertura; dados determinísticos; evidência anexada; não criar teste artificial.
Estados por página crítica (default, loading, empty, error, success, permission denied, network failure, long content,
large dataset, mobile) são exercitados combinando cenários de seed, papéis e `page.route` — ver `data-scenarios.md`.
