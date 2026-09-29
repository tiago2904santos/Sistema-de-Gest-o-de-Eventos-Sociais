# Guia do laboratório do agente

## Peças

| Peça | Onde | Faz |
|---|---|---|
| CLI | `scripts/agent/lab.py` (via `node scripts/agent/run.mjs` ou os scripts `agent:` do package.json) | bootstrap, health, serve, reset, seed, inventory, depgraph, audit, db-audit, tokens, security, doctor, command-center, manage, env |
| App `agent_lab` | `agent_lab/` (só com `AGENT_LAB=1`, padrão em DEBUG) | inventário, seed, reset, UI Lab, sonda, prévia de erros, auditorias |
| UI Lab | `/_lab/` e `/_lab/c/<id>/` | componentes reais isolados por estado; fumaça de todos os componentes |
| Sonda | `/_lab/health/` | banco, migrações pendentes, relógio, usuários do lab |
| Prévia de erros | `/_lab/erro/{403,404,500}/` | páginas de erro próprias mesmo com DEBUG |
| Playwright | `playwright.config.ts`, `tests/` | smoke, e2e, regression, a11y, visual, responsive, perf |
| Motor de auditoria | `agent_lab/audit_static.py` + `tests/tools/audit-page.mjs` | achados no formato comum |
| Comparação visual | `tests/tools/visual-compare.mjs` | before/after/diff |
| Tokens | `tokens/*.json` → `scripts/agent/build_tokens.py` | CSS `--t-*` + relatório de contraste |
| project-mcp | `tools/project-mcp/` (`.mcp.json`) | 106 ferramentas sobre tudo acima — `docs/agent/mcp.md` |
| Ambiente | `agent_lab/environment.py` (`manage.py agent_env`) | LAB/DEV/STAGING/PRODUCTION; reset só em LAB |
| Observabilidade | `agent_lab/observability.py` | `.lab/observability/*.jsonl` + `Server-Timing` |
| Doctor / self-test | `scripts/agent/doctor.py`, `tools/project-mcp/test/selftest.ts` | diagnóstico, auto-recuperação, prova ponta a ponta |

## Ambiente do servidor do laboratório

`lab.py serve` exporta: `AGENT_LAB=1`, `DJANGO_DEBUG=1`, `AGENT_LAB_FREEZE=2026-09-15T10:00:00-03:00`, banco
`.lab/lab.sqlite3` (ou `LAB_DATABASE=postgres` → `<POSTGRES_DB>_lab`), `MEDIA_ROOT=.lab/media`, eProtocolo `mock`,
geocodificação, ORS, e-mail, WhatsApp, Anthropic e banco legado **desligados**. Porta `LAB_PORT` (padrão 8031).
Na primeira subida faz `reset` no cenário `normal`; depois reaproveita (`--reset` força). Código Python mudou?
Reinicie o servidor ou use `serve --reload`.

## Usuários (senha única `Lab@2026!seguro`, só existe no banco do lab)

`lab.admin` (superusuário) · `lab.gestor_dg` · `lab.administrador` · `lab.solicitante` · `lab.viagens_gestor` ·
`lab.viagens_operador` · `lab.viagens_leitor` (módulo sem grupo = consulta) · `lab.ascom` (4 módulos ASCOM) ·
`lab.sem_modulo` (PERMISSION_DENIED) · `lab.troca_senha` (fluxo de troca obrigatória).
O `globalSetup` do Playwright faz login real com cada um e guarda a sessão em `.lab/auth/<papel>.json`.

## Cenários de dados

Ver `docs/testing/data-scenarios.md`.

## Receitas

```bash
npm run agent:bootstrap                 # do zero até o health check
npm run agent:serve                     # abre http://127.0.0.1:8031/_lab/
npm run agent:reset -- --scenario edge_case
npm test                                # todos os projetos do Playwright
npm run test:visual:update              # só depois de revisar a diferença!
node tests/tools/audit-page.mjs --path /ascom/publicacoes/ --role ascom --viewports desktop,mobile
```

## Limitações conhecidas

- O relógio ancorado troca o código de `django.utils.timezone.now` (mesmo objeto função, então `localdate()`, `localtime()`
  e `from django.utils.timezone import now` seguem a âncora); código que usa `datetime.now()`/`date.today()` direto segue no relógio real.
- Baselines visuais foram geradas em Linux (Chromium 1194). No Windows as fontes diferem: gere baselines próprias
  (`npm run test:visual:update`) ou rode o visual só no CI/Linux.
- O seed cobre as entidades principais de cada módulo, não todas as 109 (ex.: artefatos de documento, assinaturas).
