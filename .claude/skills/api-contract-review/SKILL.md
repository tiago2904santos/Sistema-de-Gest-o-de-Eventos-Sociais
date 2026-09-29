---
name: api-contract-review
description: Revisar contratos dos endpoints JSON (descoberta, schema, quebra de contrato, OpenAPI).
---

# api-contract-review

Revisar contratos dos endpoints JSON (descoberta, schema, quebra de contrato, OpenAPI).

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. `lab_reset {scenario:'normal'}` (contratos dependem do cenário).
2. `api_discover_endpoints` → `docs/api/openapi.lab.json`.
3. `api_check_contracts` → quebras (campo removido/tipo mudou) e novidades.
4. Mudança intencional → `manage.py agent_api --update` e atualizar o JS consumidor no mesmo commit.

## Saída

Relatório de quebras/novidades. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

`/viagens/termos/api/oficios/` perdeu `results[].meta` → quebra o select remoto; corrigir ou atualizar o consumidor.

## Se falhar

Endpoint quebra no lab (erro) → é achado FUNCTIONAL, não ignore.

## Pronto quando

Zero quebras não intencionais.
