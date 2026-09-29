---
name: agent-self-diagnosis
description: Diagnosticar e recuperar o próprio ambiente do agente (dependências, navegador, MCP, banco do lab, skills, agentes, docs).
---

# agent-self-diagnosis

Diagnosticar e recuperar o próprio ambiente do agente (dependências, navegador, MCP, banco do lab, skills, agentes, docs).

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. `npm run agent:doctor` (ou `agent_doctor`) — lista problemas com severidade e se são recuperáveis.
2. `npm run agent:doctor -- --fix` — aplica só reparos seguros (npm ci, instalar Chromium, recriar banco do LAB, reseed, regerar inventário/tokens).
3. Reexecute `npm run agent:doctor` e depois `npm run agent:health`.
4. O que não for recuperável: registre em `docs/agent/manual-connections.md` ou `known-problems.md`.

## Saída

Relatório `reports/agent/doctor.json` antes/depois. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

Chromium ausente após atualizar o Playwright → doctor detecta `browser` ✗ → `--fix` roda `npx playwright install chromium` → ✓.

## Se falhar

Reparo falhou → não tente variações destrutivas; reporte o comando e a saída.

## Pronto quando

Doctor sem falhas críticas e health READY.
