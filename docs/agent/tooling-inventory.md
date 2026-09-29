# Inventário de ferramentas do agente

Levantamento feito em 29/09/2026 antes de instalar qualquer coisa. Critério: **capacidade, não
quantidade** — só entra o que cobre uma lacuna real, de fonte oficial ou amplamente confiável.

## 1. O que o ambiente Claude (Cowork) já oferece

| Capacidade | Ferramenta | Uso neste projeto |
|---|---|---|
| Arquivos e shell na nuvem | Read/Write/Edit/Bash (Ubuntu 24.04) | Clonar, instalar, rodar Django/Playwright, gerar relatórios |
| Arquivos no computador do usuário | `remote-devices` (device_bash, stage/commit) | Entregar a branch no repositório local (Windows) |
| Subagentes | Agent (Explore, Plan, general-purpose) + `.claude/agents/` | Auditorias paralelas, verificação independente |
| Orquestração multi-agente | Workflow (sob pedido explícito) | Auditoria em lote de módulos |
| Navegador embutido | Claude Browser (app desktop) | Inspeção manual/visual da app local do usuário |
| Navegador do usuário | Claude in Chrome | Idem, quando pedido |
| Computer use | `computer_*` no dispositivo | Último recurso (apps Windows, Word COM) |
| Memória | memória do usuário + `docs/agent/memory/` | Decisões/descobertas persistentes |
| Projeto claude.ai | Projects | Relatórios que o time lê fora do repo |
| Publicação | Artifact | Painel de saúde/relatórios compartilháveis |
| Agendamento | scheduled tasks (create_trigger) | Health check/auditoria periódica (sugerido, não criado) |

### Plugins (marketplace oficial) — instalados pelo usuário nesta sessão

| Plugin | Origem | Traz | Por quê |
|---|---|---|---|
| **github** | GitHub (parceiro, revisado) | MCP GitHub: issues, PRs, histórico | Issues/PRs a partir de achados; hoje o push desta sessão é bloqueado (repo fora das fontes autorizadas) |
| **playwright** | Microsoft (parceiro) | MCP Playwright | Navegação exploratória pelo agente (árvore de acessibilidade, sem coordenadas) |
| **Axe Accessibility** | Deque (parceiro) | skills + MCP axe (analyze/igt/remediate) | Loop de remediação guiado; o MCP exige chave da Deque — a varredura base usa `@axe-core/playwright` (sem chave) |
| **code-review** | Anthropic | comando `/code-review` multiagente | Revisão de PR com pontuação de confiança |
| **Design** | Anthropic | skills: design-critique, design-system, accessibility-review, ux-copy, handoff | Crítica e documentação do DS |

> Os servidores MCP de plugins aparecem nas **próximas** sessões; as skills já estão ativas.
> Não instalados, por redundância ou falta de caso de uso: Figma (não há arquivos Figma — o DS vem de
> `docs/design-import/*.html`), Sentry (sem conta/instrumentação), Vercel/Render/AWS (deploy é VPS própria),
> PlanetScale (banco é PostgreSQL próprio), plugins comunitários de revisão (sobrepõem o `code-review` oficial).

## 2. Ferramentas locais adicionadas ao repositório

| Ferramenta | Versão | Onde | Papel |
|---|---|---|---|
| `@playwright/test` | 1.56.0 (fixada = browsers do ambiente) | package.json | E2E, smoke, visual, responsivo, perf |
| `@axe-core/playwright` | 4.10.2 (`playwright-core` forçado a 1.56 via `overrides`) | package.json | Acessibilidade automatizada |
| `typescript` / `@types/node` | 5.7.2 / 22.10.2 | package.json | `npm run typecheck` (modo strict) dos testes |
| `pixelmatch` + `pngjs` | 7.1.0 / 7.0.0 | package.json | Antes/depois/diff (`tests/tools/visual-compare.mjs`) |
| `ruff` | ≥0.8 | requirements-dev.txt | Lint (portão: erros de runtime) e formatação do código novo |
| `pip-audit` | ≥2.7 | requirements-dev.txt | Vulnerabilidades em dependências Python |
| `tblib` | ≥3.0 | requirements-dev.txt | Suíte paralela do Django reporta falhas em vez de quebrar |
| MCP Playwright (projeto) | `@playwright/mcp@latest` | `.mcp.json` | Para Claude Code CLI na máquina do usuário |

Nada foi instalado globalmente na máquina do usuário. No Windows, `npm run agent:bootstrap` instala
o que faltar dentro do projeto (`.venv`, `node_modules`, Chromium do Playwright).

## 3. Já existia e foi mantido

Django `TestCase` (3.054 testes), goldens DOCX/PDF, CI GitHub Actions (PG 18 + SQLite), deploy
VPS, `.claude/launch.json` (perfis de servidor no Windows), scripts de paridade em `scripts/`.

## 4. Ambiente da nuvem (referência)

Python 3.14.0rc2 (uv), Node 22.22, npm 10.9, pnpm, PostgreSQL 16, LibreOffice, Chromium 1194,
Docker CLI, mermaid-cli global. Sem `gh` e sem credencial de push para este repositório.
