# Agent health — READY

Gerado em 2026-09-29T14:16:14-03:00 · Linux-6.18.44-fc-v37-x86_64-with-glibc2.39 · python `/home/claude/cv/.venv/bin/python`

| Check | Resultado | Crítico | Detalhe | ms |
|---|---|---|---|---|
| Python + Django | ✅ | sim | 3.14.0rc2 6.1.1 | 29 |
| Dependências Python (pip check) | ✅ | não | No broken requirements found. | 250 |
| manage.py check | ✅ | sim | System check identified no issues (0 silenced). | 840 |
| Migrações sem pendência | ✅ | sim | No changes detected | 1124 |
| Banco do laboratório | ✅ | sim | sqlite /home/claude/cv/.lab/lab.sqlite3 | 1542 |
| Node/npm | ✅ | sim | node v22.22.2; npm 10.9.7 | 91 |
| node_modules | ✅ | sim | node_modules com @playwright/test e @axe-core/playwright | 0 |
| Chromium (Playwright) | ✅ | sim | chromium 141.0.7390.37 | 494 |
| Git | ✅ | não | ## agent/bootstrap-lab; 46 arquivo(s) alterado(s) | 7 |
| .env seguro | ✅ | sim | .env presente (não versionado) | 2 |
| Aplicação responde (/_lab/health/) | ✅ | sim | HTTP 200; db=sqlite; pendentes=0 | 1042 |
| MCP configurado | ✅ | não | servidores: playwright | 0 |
| Testes do agent_lab | ✅ | sim | Destroying test database for alias 'default'... | 59871 |
| Playwright smoke | ✅ | sim | [1A[2K[21/22] [smoke] › tests/smoke/health.spec.ts:22:3 › página-chave abre: relatorios (gestorDg) \| [1A[2K[22/22] [smoke] › tests/smoke/routes.spec.ts:18:1 › varredura de rotas GET sem parâmetro não devolve 5xx \|  | 27021 |
