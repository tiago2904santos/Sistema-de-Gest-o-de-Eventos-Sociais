---
name: plan-feature
description: Planejar uma funcionalidade/ferramenta antes de codar: requisitos, desenho, testes, riscos, rollback.
---

# plan-feature

Planejar uma funcionalidade/ferramenta antes de codar: requisitos, desenho, testes, riscos, rollback.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Descoberta (`agent-discovery`, `product-discovery`).
2. Escreva o plano: objetivo, fora de escopo, passos pequenos, arquivos afetados, testes (qual falha antes), evidência esperada, rollback.
3. Para processo detalhado use `superpowers:writing-plans` / `superpowers:brainstorming` (plugin Superpowers).
4. Checkpoint git antes de executar (`git_create_checkpoint`).

## Saída

Plano em Markdown (na conversa ou `docs/…` se durável). Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

Nova ferramenta de auditoria → plano com esquema de achado, teste no `agent_lab/tests.py`, registro no tool-registry.

## Se falhar

Requisito ambíguo que muda o resultado → pergunte ao usuário antes de codar.

## Pronto quando

Plano aprovado (ou autoexplicativo) e checkpoint criado.
