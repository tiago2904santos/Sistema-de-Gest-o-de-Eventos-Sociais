# Estado inicial do bootstrap do agente

> Checkpoint registrado **antes** de qualquer alteração pela missão de infraestrutura.

| Item | Valor |
|---|---|
| Data | 2026-09-29 (America/Sao_Paulo) |
| Repositório | `https://github.com/tiago2904santos/Sistema-de-Gest-o-de-Eventos-Sociais` |
| Cópia de trabalho do usuário | `C:\Users\tiago\OneDrive\Documentos\Solicitações de eventos` (Windows) |
| Branch base | `main` |
| Commit base | `53dbf3fe7649b764b1abb6233ef19d82fee086f2` — "Merge branch 'main' of …" (29/09/2026 13:12 −03) |
| Branch desta missão | `agent/bootstrap-lab` |
| Histórico | 531 commits; 14 branches remotas (várias `claude/*` e `main-*` de sessões anteriores) |
| Rollback | `git checkout main` — nada desta missão toca `main` |

## Stack detectada

| Camada | Detectado |
|---|---|
| Backend | Django 6.1 (monólito, 27 apps de domínio), Python 3.14 |
| Frontend | Django Templates (274 `.html`), CSS próprio (~9,8 mil linhas: `design-system.css`, `ds-v32.css`, `ds-v32-bridge.css`), JS vanilla (~14,9 mil linhas, sem bundler) |
| Vendor front | FullCalendar, Leaflet, pdf.js, Google Sans (em `static/vendor`) |
| Banco | PostgreSQL (produção/CI, PG 18 no CI) com fallback SQLite; banco `legado` somente-leitura para migração do GV |
| Documentos | docxtpl/python-docx/docxcompose, WeasyPrint, fpdf2, reportlab, pypdf, LibreOffice/Word COM opcionais |
| Servidor | waitress (Windows) / gunicorn (Linux) + WhiteNoise |
| Integrações | eProtocolo PR (mock por padrão), OpenRouteService, OpenStreetMap (geocodificação), WhatsApp Cloud API, Anthropic API (assistente, opcional), SMTP |
| Testes | Django `TestCase` (~1.000+ testes, ~70 mil linhas); goldens DOCX/PDF |
| CI/CD | GitHub Actions: `ci.yml` (check, makemigrations --check, testes em PG e SQLite) e `deploy-vps.yml` |
| Docker | nenhum |
| Node / package.json | nenhum no projeto |
| Lint/format/type | nenhum configurado |

## Ambiente do agente (nuvem)

- Ubuntu 24.04, Python 3.14.0rc2 via `uv`, Node 22.22, npm 10.9, pnpm, PostgreSQL 16, LibreOffice, Chromium (Playwright 1.56 / chromium-1194), Docker CLI.
- Cópia do repositório clonada do GitHub (público). **Push bloqueado**: o repositório não está entre as fontes autorizadas desta sessão — a entrega vai por bundle/branch local.

## Estado inicial

- `manage.py check`: sem problemas. `makemigrations --check`: nada pendente. `migrate` em PG 16 limpo: OK (23 s).
- Documentação existente rica em `docs/` (plano mestre da unificação, auditorias, paridade, design-import). Nenhum `CLAUDE.md`/`AGENTS.md`.
- `.claude/launch.json` já define perfis de servidor local (Windows).
