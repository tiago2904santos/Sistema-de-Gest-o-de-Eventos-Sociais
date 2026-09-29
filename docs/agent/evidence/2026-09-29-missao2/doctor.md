# agent:doctor — HEALTHY

2026-09-29T16:02:35 · 0 falha(s) crítica(s), 0 aviso(s)

| Área | Check | OK | Crítico | Detalhe |
|---|---|---|---|---|
| runtime | Python + Django (.venv) | ✅ | sim | 3.14.0rc2 6.1.1 |
| runtime | node | ✅ | sim | v22.22.2 |
| runtime | npm | ✅ | sim | 10.9.7 |
| runtime | git | ✅ | não | git version 2.43.0 |
| deps | node_modules completo | ✅ | sim | ok |
| deps | ruff instalado e em requirements-dev | ✅ | não | ok |
| deps | bandit instalado e em requirements-dev | ✅ | não | ok |
| deps | pip-audit instalado e em requirements-dev | ✅ | não | ok |
| config | @playwright/test = playwright-core (axe usa o mesmo core) | ✅ | sim | test=1.56.0 core=1.56.0 |
| browser | Chromium do Playwright abre | ✅ | sim | 141.0.7390.37 |
| mcp | .mcp.json válido | ✅ | sim | project-mcp, playwright |
| mcp | comando do servidor 'project-mcp' existe | ✅ | sim | npx |
| mcp | comando do servidor 'playwright' existe | ✅ | sim | npx |
| plugins | plugins sincronizados | ✅ | não | 9: Create, customize, and manage plugins ta; Official GitHub MCP server for repositor; Browser automation and end-to-end testin; Deque's accessibility toolkit for coding; Automated |
| skills | 55 skills válidas | ✅ | sim | ok |
| agents | 23 agentes válidos | ✅ | sim | ok |
| agents | pipelines do orquestrador coerentes | ✅ | sim | ok |
| scripts | 34 scripts npm apontam para algo que existe | ✅ | sim | ok |
| config | ferramentas usadas no CI estão em requirements-dev | ✅ | sim | ok |
| config | agent_lab só com AGENT_LAB (desligado em produção) | ✅ | sim | config/settings.py |
| database | banco do laboratório é LAB (marca interna) | ✅ | sim | LAB · /home/claude/cv/.lab/lab.sqlite3 |
| database | volume do cenário 'normal' íntegro | ✅ | sim | esperado 25, encontrado 25 |
| database | sem migrações pendentes/faltando | ✅ | sim | pendentes=0 faltando=False |
| inventory | inventário atualizado em relação ao código | ✅ | não | ok |
| docs | sem drift de documentação | ✅ | não | ok |
| dead | sem ferramentas mortas/órfãs | ✅ | não | {"orphan_skills": [], "orphan_agents": [], "unused_dev_dependencies": [], "undocumented_npm_scripts": []} |

## Reparos aplicados

- reset: recria SÓ o banco do laboratório (.lab/) e semeia → ok
- migrate: aplica migrações no banco do LAB → ok
- inventory: regera ui-inventory/ → ok
