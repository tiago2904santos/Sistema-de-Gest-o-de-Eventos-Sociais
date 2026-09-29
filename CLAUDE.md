# CLAUDE.md — como trabalhar neste repositório

Sistema de Gestão de Eventos Sociais (PCPR) — monólito Django 6.1 / Python 3.14 que
unifica Eventos Sociais, ASCOM e o domínio de Viagens (ex-Central de Viagens 3).
Leia também [`AGENTS.md`](AGENTS.md) (regras comuns a qualquer agente).

## Antes de mexer em qualquer coisa

1. `docs/README.md` — mapa da documentação (fonte da verdade).
2. `docs/agent/memory/` — decisões, descobertas, correções, problemas conhecidos, padrões aprovados/rejeitados.
3. `ui-inventory/summary.json` e o arquivo do tema (`routes.json`, `entities.json`, `components.json`…).
4. A skill do tipo de tarefa em `.claude/skills/` e, se for delegar, o agente em `.claude/agents/`.

## Comandos essenciais

| O quê | Comando |
|---|---|
| Preparar tudo (idempotente) | `npm run agent:bootstrap` (ou `python scripts/agent/lab.py bootstrap`) |
| Saúde do ambiente | `npm run agent:health` → `reports/agent-health.md` |
| Subir o laboratório | `npm run agent:serve` → http://127.0.0.1:8031/_lab/ |
| Estado previsível | `npm run agent:reset -- --scenario normal` (empty, small, normal, large, very_large, edge_case, long_text, missing_data, invalid_data) |
| Inventário / dependências / auditoria estática | `npm run agent:inventory` · `agent:depgraph` · `agent:audit` |
| Auditar uma página | `node tests/tools/audit-page.mjs --path /viagens/oficios/ --role viagensGestor` |
| Antes/depois visual | `node tests/tools/visual-compare.mjs <antes> <depois>` |
| Testes Django | `.venv/bin/python manage.py test --parallel 8` (Windows: `.venv\Scripts\python`) |
| Testes de navegador | `npm test` ou `npm run test:{smoke,e2e,a11y,visual,responsive,perf}` |

## Regras que não se negociam

- **Nunca** leia, copie ou commite `.env`, tokens ou credenciais. O laboratório não precisa deles.
- O laboratório usa banco próprio (`.lab/lab.sqlite3` ou `<db>_lab`); `agent_reset`/`agent_seed` só rodam em ambiente **LAB** (marca gravada dentro do banco) ou em banco novo do lab — ver `agent_lab/environment.py` (`manage.py agent_env`).
- Integrações externas ficam desligadas no lab (eProtocolo = mock, sem geocodificação, sem e-mail real).
- Suíte verde **não é** tela conferida: toda mudança de UI passa pelo ciclo de `docs/agent/design-review-loop.md` (captura antes/depois, axe, responsivo).
- Catracas (`tests/a11y/baseline.json`, `tests/responsive/baseline.json`, snapshots visuais) só podem **melhorar**. Atualize baseline apenas depois de revisar a diferença.
- Checkpoint git antes de mudança arriscada; commits pequenos e verificáveis (`docs/engineering/git-workflow.md`).
- Registre decisões e descobertas em `docs/agent/memory/` no mesmo commit.

## Arquitetura em uma linha

Django é o núcleo de domínio (3.054 testes, regras de dinheiro/numeração/documentos). A evolução
de frontend é **dentro** do monólito: Design System v4 tokenizado + componentes de template
+ JS em módulos — ver `docs/architecture/adr/0001-arquitetura-alvo.md`.
