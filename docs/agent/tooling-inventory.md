# Inventário de ferramentas do agente

Atualizado na missão 2 (29/09/2026). Registro de máquina: [`tool-registry.json`](tool-registry.json) (54 entradas com
purpose, source, version, status, risk, dependencies, manual_connection, replacement). Critério: **máxima capacidade com o
mínimo de redundância** — cada lacuna foi procurada em ferramenta oficial → plugin → MCP → skill → subagente → e só então criada.

## Classificação

| Ferramenta | Categoria | Classificação | Estado | Substituto |
|---|---|---|---|---|
| project-mcp | agent | CORE | READY | — |
| agent_lab (app Django) | agent | CORE | READY | — |
| scripts/agent/lab.py | agent | CORE | READY | — |
| agent:doctor | agent | CORE | READY | — |
| agent:self-test | agent | CORE | READY | — |
| skills do projeto (55) | agent | CORE | READY | — |
| subagentes (23) | agent | CORE | READY | — |
| pipelines do orquestrador (8) | agent | CORE | READY | — |
| Superpowers | agent | USEFUL | READY | — |
| Workflow (multiagente) | agent | OPTIONAL | READY | — |
| browser_* (project-mcp) | browser | CORE | READY | — |
| @playwright/test | testing | CORE | READY | — |
| Chromium (Playwright) | browser | CORE | READY | — |
| Playwright MCP (plugin Microsoft) | browser | REDUNDANT | UNAVAILABLE | browser_* do project-mcp |
| Claude Browser (app desktop) | browser | USEFUL | READY | browser_* para evidência reprodutível |
| Claude in Chrome | browser | OPTIONAL | READY | — |
| @axe-core/playwright | testing | CORE | READY | — |
| Axe MCP (plugin Deque) | testing | OPTIONAL | REQUIRES_MANUAL_CONNECTION | audit_accessibility + @axe-core/playwright |
| pixelmatch + pngjs | testing | CORE | READY | — |
| Lighthouse | testing | UNNECESSARY | UNAVAILABLE | audit_performance + tests/perf (LCP/CLS/bytes/Server-Timing) |
| Design (plugin Anthropic) | design | USEFUL | READY | — |
| Figma (plugin + conector) | design | OPTIONAL | REQUIRES_MANUAL_CONNECTION | UI Lab + tokens DTCG + Design artifact |
| tokens DTCG + build_tokens.py | design | CORE | READY | — |
| UI Lab (/_lab/) | design | CORE | READY | — |
| MagicPath | design | UNNECESSARY | UNAVAILABLE | prototype-ui (UI Lab / Design artifact / Figma) |
| WebSearch/WebFetch | research | CORE | READY | — |
| Context7 (plugin + conector) | research | USEFUL | REQUIRES_MANUAL_CONNECTION | código instalado (.venv/node_modules) + WebFetch na doc oficial |
| Tavily | research | REDUNDANT | UNAVAILABLE | WebSearch/WebFetch nativos |
| knowledge_* (project-mcp) | documentation | CORE | READY | — |
| Projects (claude.ai) | documentation | USEFUL | READY | — |
| git_* (project-mcp) | git | CORE | READY | — |
| GitHub MCP (plugin/conector) | git | USEFUL | REQUIRES_MANUAL_CONNECTION | git local + bundle entregue na pasta do usuário |
| code-review (plugin Anthropic) | git | USEFUL | READY | — |
| Django test runner | backend | CORE | READY | — |
| db_* (project-mcp) / agent_db | database | CORE | READY | — |
| environment.py (LAB/DEV/STAGING/PRODUCTION) | database | CORE | READY | — |
| MCP de Postgres | database | UNNECESSARY | UNAVAILABLE | db_* do project-mcp (respeita ambiente) |
| api_* (project-mcp) / agent_api | backend | CORE | READY | — |
| obs_* + ObservabilidadeMiddleware | observability | CORE | READY | — |
| Sentry | observability | OPTIONAL | UNAVAILABLE | observabilidade local do lab; LOGGING estruturado recomendado |
| ruff | frontend | CORE | READY | — |
| bandit | security | CORE | READY | — |
| manage.py check --deploy | security | CORE | READY | — |
| pip-audit | security | CORE | READY | — |
| npm audit | security | CORE | READY | — |
| gitleaks (CI) | security | CORE | READY | — |
| Dependabot | security | CORE | READY | — |
| Semgrep / CodeQL | security | OPTIONAL | UNAVAILABLE | bandit (Python) + auditoria estática do lab; CodeQL pode ser ligado no GitHub sem custo |
| Scanner de container/IaC (Trivy/Checkov) | security | UNNECESSARY | UNAVAILABLE | não há Dockerfile/IaC no projeto |
| deploy-vps.yml | deployment | USEFUL | READY | — |
| Vercel/Render/AWS MCPs | deployment | UNNECESSARY | UNAVAILABLE | deploy próprio (VPS/Windows) |
| scheduled tasks (claude.ai) | deployment | OPTIONAL | READY | — |
| TypeScript (tsc strict) | frontend | CORE | READY | — |
| tsx | frontend | CORE | READY | — |

## O que a re-auditoria descobriu

- **MCPs de plugin não sobem na sessão Cowork na nuvem.** github, playwright, context7, figma e axe aparecem instalados (9
  plugins sincronizados), mas os diretórios de plugins só-MCP ficam vazios e `RefreshMcpTools` não lista seus servidores.
  Skills de plugin funcionam (Superpowers, Design, Axe, Figma, code-review). Por isso a capacidade de navegador/MCP do
  agente foi construída **no próprio repositório** (`project-mcp`), que funciona aqui e no Claude Code CLI.
- **Egress**: `mcp.context7.com` e `context7.com` bloqueados pelo proxy desta sessão; PyPI e npm liberados.
- **Pesquisa web**: escolhido **WebSearch/WebFetch nativos** (sem chave, já disponíveis). Tavily avaliado e rejeitado como redundante.
- **MagicPath**: rejeitado — canvas de componentes React de terceiros não se aplica a um front Django server-rendered; protótipos
  vão no UI Lab (espécimes com tokens reais) ou em artefato Design; skill `prototype-ui`.
- **design-superpowers / ux-superpowers / ZSL Superpowers**: comunitários e sobrepostos ao Superpowers + Design → rejeitados.

## Adicionado nesta missão

`project-mcp` (106 ferramentas), `@modelcontextprotocol/sdk` 1.31, `zod` 3, `tsx` 4.23, `@types/pngjs`, `bandit`;
comandos `agent:doctor`, `agent:doctor:fix`, `agent:self-test`, `agent:security`, `agent:command-center`, `agent:db-audit`,
`agent:tokens`, `mcp:sanity`, `mcp:project`; `manage.py agent_query|agent_env|agent_db|agent_api`.
