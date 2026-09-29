---
name: agent-tool-selection
description: Escolher a ferramenta mais específica para uma capacidade, evitando redundância (política em docs/agent/tool-selection-policy.md).
---

# agent-tool-selection

Escolher a ferramenta mais específica para uma capacidade, evitando redundância (política em docs/agent/tool-selection-policy.md).

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Nomeie a capacidade (ex.: "contraste de uma página").
2. `agent_select_tool {capability}` → melhor ferramenta + alternativas do registro (`docs/agent/tool-registry.json`).
3. Prefira: ferramenta do project-mcp > script do lab > plugin/skill externo > ferramenta genérica (Bash/WebFetch).
4. Se a escolhida estiver `UNAVAILABLE`/`REQUIRES_MANUAL_CONNECTION`, use a `replacement` do registro.

## Saída

Ferramenta escolhida + justificativa em uma linha. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

"ver se a página transborda no celular" → `audit_responsive` (não screenshot manual + opinião).

## Se falhar

Nenhuma ferramenta cobre → registre a lacuna em `docs/agent/memory/tooling-lessons.md` e crie a ferramenta (skill `plan-feature`).

## Pronto quando

Uma ferramenta, a mais específica, com fonte no registro.
