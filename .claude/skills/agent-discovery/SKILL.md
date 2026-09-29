---
name: agent-discovery
description: Orientar-se no projeto no início de qualquer tarefa: estado do git, ambiente, laboratório, memória e ferramentas disponíveis. Use antes de começar trabalho não trivial.
---

# agent-discovery

Orientar-se no projeto no início de qualquer tarefa: estado do git, ambiente, laboratório, memória e ferramentas disponíveis. Use antes de começar trabalho não trivial.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. `git_status` (ou `git status`) — branch certa? nada de trabalho na `main`.
2. `project_inspect_project` — stack, ambiente (LAB/DEV/…), módulos, contagens.
3. `knowledge_search_known_problems` e `docs/agent/memory/{decisions,corrections}.md` — não repetir erros conhecidos.
4. `lab_status` — servidor do lab no ar? migrações pendentes?
5. `agent_get_pipeline` — existe pipeline para este tipo de tarefa? siga-o.
6. `agent_doctor` se qualquer passo acima falhar.

## Saída

Resumo de 5 linhas: branch, ambiente, estado do lab, problemas conhecidos relevantes, pipeline escolhido. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

Tarefa "audite o módulo de ofícios" → pipeline `audit-module`, KP-04 (navegação) e KP-00 (exclusão de servidor) já conhecidos.

## Se falhar

MCP fora do ar → use os equivalentes de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`).

## Pronto quando

Contexto suficiente para escolher pipeline e ferramentas.
