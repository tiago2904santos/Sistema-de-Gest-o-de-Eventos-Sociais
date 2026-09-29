---
name: design-system-decision
description: Decidir algo do Design System (token, escala, componente, variante) com impacto medido.
---

# design-system-decision

Decidir algo do Design System (token, escala, componente, variante) com impacto medido.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Estado atual: `inventory_get_design_tokens`, `inventory_get_duplicate_components`, `reports/design/contrast.md`.
2. Proposta em `tokens/*.json` (DTCG) ou `docs/design-system/*`; `npm run agent:tokens` recompila e mede contraste.
3. Impacto: páginas/componentes que usam o token/seletor (`inventory_get_component_usage`).
4. Paleta institucional (grafite/dourado) só muda com aprovação do usuário.

## Saída

Decisão + tokens/docs atualizados + contraste conferido. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

Rótulo 11px `#777` (4,29:1) → `neutral.600` (6,21:1).

## Se falhar

Contraste reprova → ajuste o tom antes de propor.

## Pronto quando

Nenhum token novo sem uso previsto; nenhum literal fora de tokens.
