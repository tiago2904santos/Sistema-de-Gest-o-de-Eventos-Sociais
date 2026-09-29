# BOOTSTRAP-REPORT — laboratório do agente

**Data**: 29/09/2026 · **Branch**: `agent/bootstrap-lab` (a partir de `main` @ `53dbf3f`) · **Status**: laboratório operacional (health `READY`)

Esta missão construiu a infraestrutura. **Nenhuma página foi redesenhada e nenhuma regra de negócio foi alterada.** As
únicas mudanças em código de produção são três ajustes de configuração, com padrões idênticos aos anteriores (ver
"Arquivos criados/alterados").

---

## Ambiente

| Item | Máquina do usuário (Windows) | Ambiente do agente (nuvem) |
|---|---|---|
| SO | Windows (sambook2-tiago) | Ubuntu 24.04 |
| Python | 3.14 (`.venv\Scripts\python.exe`) | 3.14.0rc2 via `uv` |
| Node / pacotes | não verificado (instale Node 20+) | Node 22.22, npm 10.9 |
| Framework | Django 6.1.1 | idem |
| Frontend | Django Templates + CSS próprio (DS V3.2) + JS vanilla | idem |
| Backend | monólito Django, 27 apps | idem |
| Banco | PostgreSQL (dev/prod), SQLite fallback | PostgreSQL 16 (suíte) + SQLite (lab) |
| Repositório | `C:\Users\tiago\OneDrive\Documentos\Solicitações de eventos` | clone do GitHub |

## Ferramentas

| Tipo | Situação |
|---|---|
| Plugins | Instalados pelo usuário a partir do catálogo oficial: **github**, **playwright**, **Axe Accessibility**, **code-review**, **Design** (+ cowork-plugin-management já existente). Skills ativas; os MCPs dos plugins carregam na próxima sessão |
| MCPs | `.mcp.json` do projeto com Playwright MCP; GitHub MCP via plugin; banco via `manage.py shell/dbshell` (MCP oficial de Postgres arquivado) — `docs/agent/mcp-architecture.md` |
| Skills | 34 em `.claude/skills/` (auditorias, design, migração, QA, git) |
| Agentes | 18 em `.claude/agents/` (architecture … final-verifier) |
| Hooks/permissões | `.claude/settings.json` nega ler/editar `.env`, `backups/`, `media/` |
| Navegador | Playwright 1.56 + Chromium 141; Claude Browser e Claude in Chrome disponíveis na sessão |
| Testes | Django (3.072 testes) + Playwright (220 testes em 7 projetos) |
| Acessibilidade | `@axe-core/playwright` 4.10.2, catraca por página, teste de teclado |
| Visual | `toHaveScreenshot` (57 baselines: 35 espécimes + grade de ícones + 21 páginas) + `visual-compare.mjs` (before/after/diff com pixelmatch) |
| Desempenho | vitals de laboratório no Playwright (TTFB, LCP, CLS, long tasks, bytes, bloqueantes) |
| Segurança | ruff (portão crítico), pip-audit, npm audit, gitleaks no CI, Dependabot |

## Arquitetura atual (resumo)

Monólito Django 6.1 com domínio rico e bem testado (regras de diárias, numeração oficial, documentos DOCX/PDF com goldens,
autorização por Setor ↔ Módulo, auditoria imutável). Frontend server-rendered com três gerações de CSS concorrentes e sem
escalas. 600 rotas, 201 páginas, 40 componentes, 62 formulários, 109 modelos. Um ciclo de imports envolve 19 apps.
Detalhes: `docs/architecture/current-architecture.md`.

## Arquitetura recomendada

**Manter Django como núcleo e reconstruir a camada de apresentação dentro do monólito** (DS v4 tokenizado, componentes com
contrato, casco novo convivendo com o atual, migração página a página com paridade, JS em módulos). SPA/Next.js/greenfield
foram avaliados e rejeitados por ora, com gatilhos explícitos de reavaliação. `docs/architecture/adr/0001-arquitetura-alvo.md`
(status: **proposta**, aguarda sua ratificação).

## Arquivos criados/alterados (280 no total vs `main`)

**Alterados (produção, sem mudança de comportamento padrão)**
- `config/settings.py` — `AGENT_LAB` (instala `agent_lab` só com DEBUG, desligado em produção); `SQLITE_PATH` opcional; `GEOCODIFICAR_SOB_DEMANDA` pode ser desligado por variável.
- `config/urls.py` — inclui `/_lab/` somente quando `AGENT_LAB` está ligado.
- `.gitignore` — `.lab/`, `node_modules/`, `reports/`.

**Criados**
- Raiz: `CLAUDE.md`, `AGENTS.md`, `.mcp.json`, `package.json`, `package-lock.json`, `playwright.config.ts`, `tsconfig.json`, `pyproject.toml`, `requirements-dev.txt`.
- `agent_lab/` — `inventory.py`, `depgraph.py`, `audit_static.py`, `db_audit.py`, `seed.py`, `specimens.py`, `clock.py`, `views.py`, `urls.py`, templates do UI Lab, `tests.py` (17 testes), `test_known_bugs.py`, comandos `agent_inventory`, `agent_depgraph`, `agent_audit_static`, `agent_db_audit`, `agent_seed`, `agent_reset`.
- `scripts/agent/` — `lab.py` (CLI), `run.mjs` (lançador multiplataforma), `build_tokens.py`.
- `tests/` — `support/` (fixtures, papéis, páginas-chave, viewports, axe, layout), `smoke/`, `e2e/`, `regression/`, `a11y/` (+ `baseline.json`), `visual/specs` + `visual/snapshots` (57 PNG), `responsive/` (+ `baseline.json`), `perf/`, `tools/` (`audit-page.mjs`, `visual-compare.mjs`, `summarize.mjs`, `layout-source.mjs`).
- `tokens/` — 9 arquivos DTCG; `static/css/tokens.css` (gerado, ainda não carregado pelo produto).
- `ui-inventory/` — 18 JSON (routes, pages, components, forms, tables, modals, dialogs, navigation, permissions, integrations, entities, documents, tokens, assets, styles, states, duplication-report, summary).
- `docs/` — `README.md`; `agent/` (bootstrap-state, tooling-inventory, mcp-architecture, lab-guide, audit-engine, audit-finding.schema.json, design-review-loop, security-rules, observability, command-center, memory/ ×8, evidence/2026-09-29/, este relatório); `architecture/` (README, current-architecture, adr/0001, migration-matrix, parity-testing); `design-system/` (23 arquivos); `product/`, `ux/`, `engineering/` (4), `testing/` (2), `integrations/`, `data/`.
- `.claude/skills/` (34 × `SKILL.md`), `.claude/agents/` (18), `.claude/settings.json`.
- `.github/workflows/agent-lab.yml`, `.github/dependabot.yml`.

## Dependências instaladas

- **Node (devDependencies, só no projeto)**: `@playwright/test` 1.56.0, `@axe-core/playwright` 4.10.2 (com `overrides` de `playwright-core` 1.56.0), `typescript` 5.7.2, `@types/node` 22.10.2, `pixelmatch` 7.1.0, `pngjs` 7.0.0.
- **Python (requirements-dev.txt)**: `tblib`, `ruff`, `pip-audit`.
- Nada de produção mudou em `requirements.txt`.

## Comandos criados

| npm | equivalente | faz |
|---|---|---|
| `agent:bootstrap` | `lab.py bootstrap [--force] [--quick]` | venv, deps Python/Node, Chromium, banco do lab + seed, inventário, grafo, health |
| `agent:health` / `agent:health:quick` | `lab.py health` | 14 checagens → `reports/agent-health.md` |
| `agent:serve` | `lab.py serve [--reset] [--reload] [--port]` | Django do laboratório em :8031 |
| `agent:reset` / `agent:seed` | `lab.py reset|seed --scenario …` | estado previsível / cenário adicional |
| `agent:inventory` · `agent:depgraph` · `agent:audit` · `agent:db-audit` · `agent:tokens` · `agent:env` | idem | inventário, dependências, auditoria estática, banco, tokens, ambiente |
| `test` · `test:smoke|e2e|a11y|visual|responsive|perf` · `test:visual:update` · `test:a11y:baseline` · `test:report` · `typecheck` | Playwright/TS | camadas de teste |
| `audit:page` | `node tests/tools/audit-page.mjs` | auditoria de uma página com evidência |
| — | `node tests/tools/visual-compare.mjs A B` | before/after/diff |
| — | `manage.py agent_seed|agent_reset|agent_inventory|agent_depgraph|agent_audit_static|agent_db_audit` | comandos Django do lab |

## Testes realizados (resultados reais)

| Teste | Resultado |
|---|---|
| Suíte Django no `main` antes da missão (PG 16, `--parallel 8`) | 3.054 testes, **14 falhas pré-existentes** (12 textos de paginação desatualizados, 2 OCR sem tesseract), 5 skips |
| Suíte Django depois (PG 16) | 3.072 testes (+18 do lab), **as mesmas 14 falhas, nenhuma nova**, 1 expectedFailure (KP-00) |
| `agent_lab` (Django) | 17/17 + 1 expectedFailure |
| Playwright completo (7 projetos) | **220 passaram, 0 falharam, 0 flaky** (4 min 18 s) |
| Visual reexecutado | 24/24 idênticos à baseline (determinismo comprovado) |
| Bootstrap num clone limpo, sem `.env` | **READY** em 2 min 18 s |
| Bootstrap repetido (idempotência) | READY em 13 s, sem recriar nada, `git status` limpo |
| Health check | **READY** (14/14) |
| `ruff` crítico / formatação do código novo / tokens `--check` / `tsc --strict` | todos OK |
| pip-audit / npm audit | 1 vulnerabilidade (weasyprint 69.0 → corrigida na 70.0) / 0 |

Self-test exigido pela missão (item 49): iniciar a app ✔ · abrir página ✔ · navegar ✔ · screenshot ✔ · inspecionar
estrutura (DOM/árvore/landmarks) ✔ · axe ✔ · teste de interação (login, mostrar senha, busca, permissões, falha de rede) ✔ ·
salvar evidências ✔ · executar testes ✔ · gerar relatório ✔. Evidências em `docs/agent/evidence/2026-09-29/`.

## Problemas encontrados (produto)

Lista completa e priorizada: `docs/agent/memory/known-problems.md`. Destaques:

1. **KP-00 · P1 · perda de dado** — excluir um servidor pela tela apaga em silêncio as prestações de contas dele
   (`PrestacaoServidor.servidor` = CASCADE; a checagem só olha PROTECT/RESTRICT). Reproduzido pela view no lab.
2. **KP-01 · P1** — Agenda com 5 violações axe críticas.
3. **KP-04 · P2** — navegação do módulo Viagens causa rolagem horizontal da página até em 1440px (40 de 120 combinações).
4. **KP-02/03 · P2** — foco invisível; cinzas de rótulo/metadado abaixo do contraste AA.
5. **KP-05 · P2** — `pdf-place.css` usa 13 tokens que não existem.
6. **KP-06 · P2** — `DEBUG` liga por padrão sem `.env`. **KP-13 · P2** — weasyprint 69.0 vulnerável.
7. **KP-09** — 14 testes quebrados no `main`.

## Problemas que exigem intervenção manual

1. **Push**: esta sessão não tem credencial para o repositório (não está entre as fontes autorizadas). A branch foi entregue
   no seu repositório local; o push é seu (`git push -u origin agent/bootstrap-lab`) — ou autorize o repositório numa próxima sessão.
2. **Ratificar o ADR 0001** (arquitetura-alvo) antes de começar a reconstrução.
3. **Corrigir KP-00** (decisão de negócio: bloquear exclusão ou `PROTECT` via migração).
4. **No Windows**: instalar Node 20+ se não houver; rodar `npm run agent:bootstrap`. As baselines visuais foram geradas em Linux —
   gere as suas (`npm run test:visual:update`) ou deixe o visual para o CI.
5. **Axe MCP** (plugin Deque) pede chave da Deque para os comandos MCP; a varredura do laboratório não precisa.
6. Opcional: instalar `tesseract` para os 2 testes de OCR; atualizar weasyprint para 70 com os goldens de PDF.

## Próximas capacidades disponíveis

Com o que existe agora, o agente consegue, sem preparação adicional:

- Subir o sistema em estado **previsível** (9 cenários, 10 papéis, relógio ancorado) e voltar a ele com um comando.
- **Ver** qualquer página como qualquer papel, em 6 viewports, com captura, DOM, árvore de acessibilidade, console e rede.
- **Auditar** página, componente, fluxo, módulo ou banco e devolver achados P0–P4 com evidência num formato único.
- **Comparar** antes/depois (pixel diff, tamanho, axe, overflow, vitals) e barrar regressões por catraca.
- **Consultar** o produto como dados: rotas, páginas, componentes, formulários, entidades, permissões, tokens, duplicações, grafo.
- **Criar e testar componentes isolados** no UI Lab (todos os estados), com baseline visual e axe.
- **Migrar** módulo a módulo seguindo a matriz e o protocolo de paridade, com skills e subagentes especializados.
- **Registrar** o que aprende (memória versionada) e **provar** saúde do ambiente a qualquer momento (`agent:health`).

Quando você disser "reconstrua o sistema", o ponto de partida é: ratificar o ADR → tokens/casco/componentes v4 no UI Lab →
piloto (login + páginas de erro) → matriz de migração na ordem sugerida.
