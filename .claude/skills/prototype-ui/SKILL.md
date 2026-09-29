---
name: prototype-ui
description: Prototipar uma tela/componente rápido para decidir direção (sem mexer no produto).
---

# prototype-ui

Prototipar uma tela/componente rápido para decidir direção (sem mexer no produto).

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Componente: espécime novo no UI Lab (`agent_lab/specimens.py`) usando tokens `--t-*`.
2. Página: artefato do tipo Design (Artifact tool) ou Figma (quando conectado; skills `figma:*`).
3. Comparar alternativas lado a lado; evidência com `browser_capture_element`.
4. Decisão → `ux-decision`/`design-system-decision`.

## Saída

Protótipo + capturas + decisão. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

Três variantes de cabeçalho de lista como espécimes → escolha registrada.

## Se falhar

Figma sem conexão → Design artifact ou UI Lab (ver manual-connections).

## Pronto quando

Direção escolhida com evidência.
