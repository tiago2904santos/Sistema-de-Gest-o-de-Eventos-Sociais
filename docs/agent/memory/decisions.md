# Decisões

- **2026-09-29 · Manter Django como núcleo; evoluir o frontend dentro do monólito** — SPA/Next.js
  rejeitados por ora: 3.054 testes e as regras de dinheiro, numeração e documentos vivem no Django;
  os problemas medidos são de CSS/DS/HTML, não de arquitetura. Evidência: `docs/architecture/adr/0001-arquitetura-alvo.md`.
- **2026-09-29 · Laboratório isolado em app `agent_lab`** instalado só com `AGENT_LAB` (padrão = DEBUG).
  Produção não carrega nada dele. Evidência: `config/settings.py`, `agent_lab/tests.py::LabViewsTests`.
- **2026-09-29 · Banco próprio do laboratório** (`.lab/lab.sqlite3` padrão; `LAB_DATABASE=postgres` → `<db>_lab`)
  para nunca tocar o banco de desenvolvimento nem o `db.sqlite3` do dev. Evidência: `scripts/agent/lab.py::lab_env`.
- **2026-09-29 · Relógio ancorado (2026-09-15 10:00 −03)** no servidor (`AGENT_LAB_FREEZE`) e no navegador
  (`clock.setFixedTime`) — telas com "há N dias"/"começa hoje" ficam estáveis para captura. Evidência: baselines visuais repetíveis.
- **2026-09-29 · Catracas em vez de portões binários** para a11y e overflow: a dívida atual é registrada
  (`tests/a11y/baseline.json`, `tests/responsive/baseline.json`) e só pode diminuir. Motivo: CI verde e útil desde o dia 1.
- **2026-09-29 · Tokens no formato W3C DTCG** em `tokens/*.json`, compilados para `static/css/tokens.css` com prefixo `--t-`
  (convive com `ds-v32.css`). Ainda não carregado pelo produto.
- **2026-09-29 · Não reformatar o código existente com ruff** (777 arquivos): diff gigante sem ganho funcional.
  Portão do CI só em erros de runtime (E9/F63/F7/F82); o resto é relatório.
- **2026-09-29 · Playwright fixado em 1.56.0** para casar com os browsers pré-instalados; `playwright-core` forçado via `overrides`
  porque o `@axe-core/playwright` puxava 1.63 e quebrava os tipos.
- **2026-09-29 · Missão 2** — ver `tooling-decisions.md` (MCP consolidado, ambiente por marca interna, pesquisa nativa, CI em trilhas).
