# Versões e compatibilidade

Gerado/conferido por `npm run agent:doctor` (versões reais em `reports/agent/versions.json`).

| Componente | Versão | Compatibilidade / observação |
|---|---|---|
| Python | 3.14 (nuvem: 3.14.0rc2 via uv) | Exigido pelo projeto (CI 3.14) |
| Django | 6.1.1 | `{% partialdef %}` disponível (ADR 0001) |
| Node | 22.x (mínimo 20) | tsx roda o project-mcp sem build |
| npm | 10.9 | lockfile v3 |
| @playwright/test / playwright-core | 1.56.0 / 1.56.0 (forçado por `overrides`) | Casados com o Chromium 141 (chromium-1194); **não atualizar isolado** — Dependabot ignora |
| Chromium | 141.0.7390.37 | `npx playwright install chromium` recupera |
| @axe-core/playwright | 4.10.2 | Usa o `playwright-core` do override |
| TypeScript | 5.7.2 (strict) | testes + project-mcp |
| @modelcontextprotocol/sdk | 1.31.0 | `registerTool` (API nova); zod 3.25 |
| tsx | 4.23 | executa `.ts` com imports `.ts` |
| pixelmatch / pngjs | 7.1.0 / 7.0.0 | diffs visuais |
| ruff | 0.16 | portão E9/F63/F7/F82 |
| bandit | 1.9 | catraca `tests/security/bandit-baseline.json` |
| pip-audit | 2.10 | relatório (KP-13) |
| PostgreSQL | 16 (nuvem) / 18 (CI) | lab usa SQLite por padrão; `LAB_DATABASE=postgres` → `<db>_lab` |
| Plugins | Superpowers 6.4.1 · Design 1.2.0 · Axe 0.2.0 · Figma 2.2.108 · code-review · github · playwright · context7 | MCPs de plugin não sobem na sessão Cowork na nuvem |

Regras: atualizar Playwright = atualizar `@playwright/test`, o override de `playwright-core`, reinstalar o Chromium e
regenerar baselines visuais no mesmo PR.
