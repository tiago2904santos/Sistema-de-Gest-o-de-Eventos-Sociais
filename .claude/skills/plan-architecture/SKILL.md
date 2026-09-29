---
name: plan-architecture
description: Produzir uma decisão arquitetural (ADR) com alternativas medidas.
---

# plan-architecture

Produzir uma decisão arquitetural (ADR) com alternativas medidas.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Medir: `inventory_get_dependency_graph`, `audit_static`, `db_audit`, inventário.
2. Pesquisar alternativas (`research-technical`).
3. Escrever ADR em `docs/architecture/adr/NNNN-*.md`: contexto medido, alternativas (tabela), decisão, gatilhos de reavaliação, consequências.
4. Status 'proposta' até o usuário ratificar.

## Saída

ADR novo + entrada em decisions.md. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

ADR 0001 (monólito + DS v4) é o modelo.

## Se falhar

Dados insuficientes → rode o cenário `very_large` e meça antes de decidir.

## Pronto quando

ADR com números conferíveis e gatilhos.
