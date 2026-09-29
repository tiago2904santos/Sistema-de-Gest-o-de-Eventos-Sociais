---
name: visual-diagnosis
description: Explicar POR QUE algo está visualmente errado (estilos computados, box model, regra CSS vencedora) e não só que está.
---

# visual-diagnosis

Explicar POR QUE algo está visualmente errado (estilos computados, box model, regra CSS vencedora) e não só que está.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Evidência: `browser_capture_element` + `browser_inspect_layout` (overflow/culpado).
2. Estilos: `browser_inspect_dom {selector}` e, se preciso, script no flow para `getComputedStyle`.
3. Origem da regra: `inventory_get_ui_inventory {section:'styles'|'duplication-report', filter:<seletor>}` — mesmo seletor em vários CSS?
4. Token: `inventory_get_design_tokens` — token indefinido/conflitante?
5. Corrigir na origem (token/componente), nunca com `!important` pontual.

## Saída

Diagnóstico: elemento, propriedade, regra/arquivo que vence, correção proposta. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

Navegação de Viagens transborda → `div.nav-mod` com 12 itens sem wrap em `ds-v32-bridge.css`.

## Se falhar

Não reproduz no lab → confira viewport, papel e cenário de dados (texto longo?).

## Pronto quando

Causa localizada em arquivo:regra.
