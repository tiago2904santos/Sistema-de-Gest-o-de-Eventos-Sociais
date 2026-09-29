---
name: component-contract
description: Definir/verificar o contrato de um componente de template (parâmetros, estados, acessibilidade) e mantê-lo coerente com os usos.
---

# component-contract

Definir/verificar o contrato de um componente de template (parâmetros, estados, acessibilidade) e mantê-lo coerente com os usos.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. `project_inspect_component` — contrato atual (comentário do topo) e usos.
2. Levantar parâmetros realmente usados: `inventory_get_component_usage` + grep dos `with …` nos consumidores.
3. Atualizar o comentário-contrato: parâmetros, obrigatórios, estados, exemplos.
4. Espécimes para cada estado em `agent_lab/specimens.py`; `audit_component` em cada um.

## Saída

Contrato documentado + espécimes. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

`components/select.html`: `remoto` exige `pesquisavel` — documentado e com espécime.

## Se falhar

Consumidor usa parâmetro não documentado → documente ou migre o consumidor.

## Pronto quando

Contrato = uso real, verificado.
