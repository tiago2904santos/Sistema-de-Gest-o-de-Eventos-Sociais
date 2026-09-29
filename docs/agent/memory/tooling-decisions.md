# Decisões de ferramental

- **2026-09-29 · Um MCP consolidado (`project-mcp`) em vez de três** — estado compartilhado (lab, sessões, evidências) e um processo para operar/testar. Prefixos no lugar de pontos (restrição de nome dos clientes MCP).
- **2026-09-29 · MCP em TypeScript (tsx)** — Playwright e axe são nativos em Node e o MCP importa os mesmos módulos dos testes (`roles.ts`, `viewports.ts`, `layout-source.mjs`); a parte Django entra por `manage.py agent_query` (JSON). Sem build.
- **2026-09-29 · Ambiente decidido pela marca DENTRO do banco** (`agent_lab_marcador`), não por nome de variável/banco. Declaração `APP_ENVIRONMENT` só aumenta o risco.
- **2026-09-29 · WebSearch/WebFetch nativos como pesquisa web** (Tavily rejeitado: redundante e exige chave). Context7 como conector opcional.
- **2026-09-29 · Figma e Axe MCP como opcionais com substituto ativo** (UI Lab/tokens/Design artifact; `@axe-core/playwright`).
- **2026-09-29 · bandit + `check --deploy` como SAST/config** (Semgrep/CodeQL opcionais; Trivy/Checkov desnecessários — sem container/IaC).
- **2026-09-29 · CI em trilhas fast/full/nightly** — PR rápido; visual/perf/self-test em main; dependências/segredos/drift à noite. Scheduled tasks do claude.ai não ativadas (o nightly do GitHub cobre).
- **2026-09-29 · Agentes com ferramentas explícitas** (`mcp__project-mcp__*` por papel) — menor privilégio e validação pelo doctor.
