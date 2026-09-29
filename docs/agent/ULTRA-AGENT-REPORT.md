# ULTRA-AGENT-REPORT — missão 2 (expansão da infraestrutura do agente)

**Data**: 29/09/2026 · **Branch**: `agent/bootstrap-lab` · checkpoint antes da missão: tag `checkpoint/20260929-pre-missao2`
**Resultado**: doctor **HEALTHY** · health **READY** · self-test pelo MCP **19/19** · Playwright **220/220** · Django **3.081 testes, sem falha nova**.
**Produto**: nenhuma página redesenhada, nenhum módulo migrado, nenhuma regra alterada. Mudanças em código de produção: uma
linha em `config/settings.py` (middleware de observabilidade inserido só quando `AGENT_LAB` está ligado, desligado em produção).

---

## Environment

| Item | Valor |
|---|---|
| Nuvem do agente | Ubuntu 24.04 · Python 3.14.0rc2 (uv) · Django 6.1.1 · Node 22.22 · npm 10.9 · Chromium 141 · PostgreSQL 16 |
| Máquina do usuário | Windows (sambook2-tiago) · repositório em `…\Documentos\Solicitações de eventos` |
| Laboratório | Django em :8031, banco LAB `.lab/lab.sqlite3` com marca interna, relógio ancorado em 15/09/2026 10:00 −03 |
| Egress desta sessão | PyPI/npm liberados; `context7.com`/`mcp.context7.com` bloqueados; push para o GitHub bloqueado (repo fora das fontes) |

## Installed plugins

Superpowers (6.4.1), context7, Figma (2.2.108) — instalados nesta missão; já existiam: github, playwright, Axe Accessibility,
code-review, Design, cowork-plugin-management. **9 no total.**

## Connected plugins

| Plugin | Skills nesta sessão | MCP nesta sessão |
|---|---|---|
| Superpowers | ✅ 15 skills | — (não tem) |
| Design | ✅ 7 skills | — |
| Axe Accessibility | ✅ 4 skills | ❌ exige chave Deque |
| Figma | ✅ 14 skills | ❌ exige OAuth (conector) |
| code-review | ✅ `/code-review` | — |
| github, playwright, context7 | — | ❌ MCP remoto de plugin não sobe na sessão Cowork na nuvem (conferido com `RefreshMcpTools`) |

Detalhes e o que conectar: [`manual-connections.md`](manual-connections.md).

## MCPs

**project-mcp** (novo, `tools/project-mcp`, TypeScript/stdio, registrado em `.mcp.json`): **106 ferramentas** em 13 namespaces —
`project_` 9, `inventory_` 10, `lab_` 6, `testing_` 9, `browser_` 22, `audit_`+`compare_` 12, `knowledge_` 12, `git_` 4,
`report_` 5, `db_` 6, `api_` 2, `obs_` 4, `agent_` 5. Os três MCPs sugeridos (central-viagens, browser-evidence,
project-knowledge) foram **consolidados** num servidor (estado compartilhado, um processo). Ciclo de validação:

| Etapa | project-mcp |
|---|---|
| DISCOVERED → CONFIGURED | `.mcp.json` |
| CONNECTED | `npm run mcp:sanity` (handshake + 2 chamadas) — também no CI e no doctor |
| CALLED → WORKED | `npm run agent:self-test` — 19 passos, 31 ferramentas distintas chamadas, todas com asserção de resultado |
| DOCUMENTED | [`mcp.md`](mcp.md) |

`playwright` (Microsoft) segue no `.mcp.json` para o Claude Code CLI; é redundante com `browser_*`.

## Skills

**55** (34 revisadas + 21 novas), todas validadas pelo doctor (frontmatter, *Passos*, *Se falhar*, comandos e ferramentas MCP
citadas existem). Novas: agent-discovery, agent-tool-selection, agent-self-diagnosis, research-technical, research-library,
plan-feature, plan-architecture, browser-evidence, visual-diagnosis, ux-decision, design-system-decision, component-contract,
bug-reproduction, bug-fix-verification, security-review, dependency-review, api-contract-review, database-review, rollback,
incident-analysis, prototype-ui. Nomes da missão mapeados em vez de duplicados: technical-research → research-technical,
plan-migration → migration-planning, regression-investigation → regression-analysis, release-readiness → release-validation.
Integração com o Superpowers: [`superpowers-integration.md`](superpowers-integration.md).

## Agents

**23**, com ferramentas explícitas (`mcp__project-mcp__*` por papel). Novos: tooling-architect, research-agent, api-agent,
incident-agent, frontend-architect, frontend-implementer, backend-architect, backend-implementer. Renomeados/fundidos:
product-agent → product-discovery-agent, ux-agent → ux-research-agent, visual-agent + responsive-agent → design-agent.
Orquestração: **8 pipelines** (`docs/agent/pipelines/`: full-chain, audit-module, redesign-page, rewrite-component,
investigate-bug, migrate-module, rebuild-system, evaluate-architecture) — [`workflows.md`](workflows.md).

## Hooks

`.claude/settings.json` nega ler/editar `.env`, `backups/`, `media/`. Hook `SessionStart` do Superpowers (carrega
`using-superpowers`). Hooks de sessão do ambiente (checagem de git no Stop) mantidos. Nenhum hook novo de escrita automática.

## Scripts

`npm run` (34): `agent:bootstrap|health|health:quick|serve|reset|seed|inventory|depgraph|audit|db-audit|tokens|security|doctor|doctor:fix|self-test|command-center|env`,
`mcp:project|sanity`, `test|test:smoke|e2e|a11y|visual|visual:update|responsive|perf|report|a11y:baseline`, `typecheck`, `audit:page`,
`posttest:*`. Django: `agent_query`, `agent_env`, `agent_db`, `agent_api`, `agent_db_audit`, `agent_seed` (com cenários sob medida),
`agent_reset`, `agent_inventory`, `agent_depgraph`, `agent_audit_static`.

## Tool registry

[`tool-registry.json`](tool-registry.json): **54 ferramentas** com name, category, purpose, source, version, status, classification,
risk, dependencies, manual_connection, replacement. Consulta pelo agente: `agent_select_tool`. Política: [`tool-selection-policy.md`](tool-selection-policy.md).

## Security

`npm run agent:security`: bandit com **catraca** (baseline; achado novo HIGH/MEDIUM reprova — pegou o `shell=True` do próprio
doctor, corrigido), `manage.py check --deploy` com produção simulada (**limpo**), pip-audit (**weasyprint 69.0 vulnerável**, KP-13),
npm audit (0). Banco: classificação **LAB/DEV/STAGING/PRODUCTION** pela marca interna (`agent_lab/environment.py`) — só LAB pode
ser recriado; PRODUCTION é somente leitura; `db_explain` só SELECT em transação somente-leitura. A missão **fechou uma brecha**: a
trava antiga liberava reset de qualquer SQLite, inclusive o `db.sqlite3` do dev.

## Browser

22 ferramentas `browser_*` (sessões por papel com login real e renovação automática, relógio ancorado, DOM, árvore ARIA,
landmarks, foco, console, rede, layout, capturas, viewports, teclado, fluxos com trace). Playwright 1.56 + Chromium 141.

## Design

UI Lab (`/_lab/`), tokens DTCG + contraste, skills do plugin Design, `prototype-ui`. **Figma**: plugin instalado, conector
pendente (OAuth) — [`manual-connections.md`](manual-connections.md). **MagicPath**: avaliado e **não instalado** (ver abaixo).

## Documentation

`docs/agent/`: architecture, tooling, workflows, skills, agents, mcp, security, browser, testing, recovery, troubleshooting,
manual-connections, superpowers-integration, tool-selection-policy, compatibility, command-center.schema.json, pipelines/,
tool-registry.json; memória com tooling-decisions, tooling-lessons, agent-patterns. O doctor detecta **drift** (links, caminhos,
`npm run` e `manage.py` inexistentes) — estado atual: 0.

## Research

WebSearch/WebFetch nativos (escolhidos — sem chave); `research-library` usa primeiro o **código instalado** (fonte exata da
versão), depois doc oficial. Context7 instalado, conector pendente. Busca interna: `knowledge_*` (BM25 com radical, fonte
`arquivo:linha`, cobre docs, memória, skills, agentes e docstrings de regras de negócio).

## Database

`db_environment`, `db_explain` (plano real no PG e SQLite; ANALYZE só LAB/DEV), `db_validate_migrations` (pendentes, destrutivas,
RunPython, conflitos), `db_find_anomalies`, `db_index_review`, `db_audit`; cenários sob medida (`lab_create_test_scenario`).

## Git

`git_status`, `git_diff`, `git_history`, `git_create_checkpoint` (tag; recusa com WIP). Checkpoint da missão criado. Entrega por
bundle + `git fetch` no repositório local (push bloqueado nesta sessão).

## Observability

`ObservabilidadeMiddleware` (só no lab): duração, nº de SQL, tempo de banco, consultas lentas, SQL repetido (N+1), exceções com
traceback em `.lab/observability/*.jsonl` + header `Server-Timing`. Ferramentas `obs_*`. Sentry documentado como opcional.

## CI

`.github/workflows/agent-lab.yml` em trilhas: **fast** (todo push/PR: ruff crítico, formatação, tokens, TS strict, bandit +
check --deploy, testes do agent_lab, MCP sanity, doctor rápido, Playwright smoke/e2e/regression/a11y), **full** (main/manual: +
responsive, visual, perf, self-test), **nightly** (03:17: + gitleaks, pip-audit, npm audit, drift, contratos de API). Scheduled
tasks do claude.ai não ativadas (o nightly do GitHub cobre).

## Self-healing

`npm run agent:doctor:fix`: detect → diagnose → repair → retest. **Provado**: com o banco do lab apagado e o inventário
desatualizado, aplicou `reset`, `migrate` e `inventory` e voltou a **HEALTHY** (evidência: `evidence/2026-09-29-missao2/doctor.md`).
Nenhum reparo toca banco que não seja do laboratório.

## Memory

`docs/agent/memory/`: decisions, discoveries, corrections (+2 desta missão, incluindo o bug do reset que acumulava seeds),
known-problems (KP-00…KP-16), approved/rejected-patterns, lessons-learned, **tooling-decisions**, **tooling-lessons**, **agent-patterns**.

## Health

| Verificação | Resultado |
|---|---|
| `npm run agent:doctor` | HEALTHY — 0 falha crítica, 0 aviso (skills, agentes, pipelines, scripts, drift, mortos, banco, navegador, MCP) |
| `npm run agent:health` | READY (14/14) |
| `npm run agent:self-test` | PASSOU 19/19 |
| `npm run test:smoke`, `test:a11y`, `test:visual`, todos os projetos | 220/220 |
| `npm run typecheck` | OK |
| `npm run agent:security` | bandit ✓ · check --deploy ✓ · pip-audit ✗ (weasyprint) · npm audit ✓ |
| Suíte Django (PG) | 3.081 testes; as mesmas 14 falhas pré-existentes do `main` (KP-09), nenhuma nova |
| Command Center | 17 blocos, nenhuma fonte ausente (`reports/agent/command-center.json`) |

## Known limitations

- MCPs de plugins não carregam na sessão Cowork na nuvem; o project-mcp cobre navegador/auditoria/conhecimento.
- Baselines visuais geradas em Linux; no Windows gere as suas ou deixe o visual no CI.
- Relógio ancorado não cobre `datetime.now()`/`date.today()` diretos.
- Contratos de API dependem do cenário (`normal`).
- Busca de conhecimento é lexical (BM25 + radical); não é semântica.
- `browser_submit`/`audit_form` escrevem dados — permitidos só em LAB.

## Manual connections required

GitHub (concluir conector + autorizar o repositório), Context7 (conector), Figma (OAuth + arquivo do DS), Axe MCP (chave Deque),
opcional Sentry e tesseract. Detalhes: [`manual-connections.md`](manual-connections.md).

## Tools intentionally NOT installed

| Ferramenta | Por que foi considerada | Por que foi rejeitada | Pode entrar depois? |
|---|---|---|---|
| MagicPath | prototipação/wireframes (pedido da missão) | canvas de componentes React de terceiros; front é Django server-rendered; exige conta/CLI; UI Lab + Design artifact cobrem | sim, se surgir front React |
| Tavily / Parallel Search | pesquisa web para agentes | WebSearch/WebFetch nativos já cobrem, sem chave; escolher **uma** | sim (API key) |
| design-superpowers, ux-superpowers, ZSL Superpowers | processo de design/UX | comunitários e sobrepostos a Superpowers + Design | não recomendado |
| Claude2Figma | DS no Figma | depende de Figma conectado e de biblioteca no Figma inexistente | após o Figma |
| Lighthouse | desempenho | pesado; vitals do Playwright + Server-Timing cobrem | sim (`npx lighthouse`) |
| Semgrep / CodeQL | SAST | bandit + auditoria estática cobrem Python; CodeQL grátis no GitHub se desejado | sim |
| Trivy / Checkov | container/IaC | projeto não tem Dockerfile nem IaC | quando houver |
| MCP de Postgres | SQL genérico | arquivado; ignora ambiente/routers — `db_*` é mais seguro | não |
| Sentry | erros de produção | decisão de produto + DSN; nada de infra externa só para teste | sim |
| Vercel/Render/AWS MCPs | deploy | deploy é VPS/Windows próprio | não |

## Matriz de capacidade

| Capacidade | Ferramenta | Estado |
|---|---|---|
| Browser | `browser_*` (project-mcp) + Playwright/Chromium | READY |
| Accessibility | `audit_accessibility`, `@axe-core/playwright`, catraca | READY |
| Visual | `audit_visual`, `compare_screenshots`, 57 baselines | READY |
| Design | UI Lab, tokens DTCG, plugin Design, `prototype-ui` | READY (Figma: conexão manual) |
| Research | WebSearch/WebFetch, `research-library` (código instalado), `knowledge_*` | READY (Context7: conexão manual) |
| Documentation | `docs/` + drift no doctor + `knowledge_*` | READY |
| Git | `git_*`, checkpoint, bundle | READY (push: conexão manual) |
| Database | `db_*`, ambiente por marca interna | READY |
| Security | bandit (catraca), check --deploy, pip/npm audit, gitleaks, `security-review` | READY |
| Testing | `testing_*`, Django + Playwright, full validation | READY |
| Performance | `audit_performance`, `obs_*`, `db_explain`, vitals | READY |
| Architecture | `inventory_get_dependency_graph`, `audit_static`, ADRs, pipeline evaluate-architecture | READY |
| Product | `project_inspect_*`, `knowledge_search_business_rules`, product-discovery-agent | READY |
| Migration | matriz + pipeline migrate-module + paridade | READY |
| Observability | `ObservabilidadeMiddleware` + `obs_*` + Server-Timing | READY (local) |
| MCP | project-mcp 106 ferramentas, sanity + self-test | READY |
| Agent memory | `docs/agent/memory/` (11 arquivos) + memória do usuário | READY |

**Pronto para a próxima missão.** Ponto de partida para "reconstrua o sistema": `agent_get_pipeline {name:"rebuild-system"}` —
começa pela ratificação do ADR 0001.
