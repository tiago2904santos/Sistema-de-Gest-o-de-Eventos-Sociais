# Fluxo git

- Branches: `feature/…`, `fix/…`, `refactor/…`, `chore/…`, `migration/…`, `design/…`, `agent/…`.
- Commits `tipo(escopo): resumo` (feat, fix, refactor, chore, migration, design, docs, test); corpo cita a evidência.
- **Checkpoint** antes de mudança arriscada: commit (ou `git tag checkpoint/<data>-<assunto>`).
- Migração grande = vários commits verificáveis (um módulo/página por vez), nunca um commit gigante.
- PR exige CI verde (lint crítico, testes Django PG+SQLite, testes do lab, Playwright smoke/e2e/a11y/regression).
- Nunca `push --force` em `main`; nunca commitar `.env`, `media/`, `.lab/`, `reports/`, `node_modules/`.
- Vários agentes trabalham no repositório: `settings_revisao.py` isola o banco de teste de uma revisão paralela; use-o quando houver outra suíte rodando.
