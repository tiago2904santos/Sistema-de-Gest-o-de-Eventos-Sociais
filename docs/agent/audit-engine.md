# Motor de auditoria

Entrada: **página**, **componente**, **fluxo** ou **módulo**. Saída: lista de achados com
`severity` (P0–P4), `category`, `evidence` e `recommendation` — esquema em `audit-finding.schema.json`.

| Camada | Comando | Cobre |
|---|---|---|
| Estática | `npm run agent:audit` → `reports/audit/static-findings.{json,md}` | CSS (foco removido, cores literais, `!important`, tokens inexistentes/conflitantes), templates (img sem alt, tabela sem scope, botão-ícone sem nome, `|safe`, tamanho, estilo inline), código (`csrf_exempt`, `mark_safe`, módulos gigantes, DEBUG padrão), rotas sem guarda, ciclos de import, duplicação |
| Runtime (página) | `node tests/tools/audit-page.mjs --path … --role … [--viewports …] [--click …] [--label …]` | status HTTP, exceções JS, console, requisições falhas/5xx, axe, h1/landmarks/DOM, LCP/CLS/HTML, overflow e alvos pequenos por viewport; capturas |
| Componente | `npm run test:visual` + axe no espécime (`/_lab/c/<id>/`) | visual por estado, render sem erro |
| Fluxo | spec em `tests/e2e/` | comportamento de ponta a ponta |
| Módulo | laço de `audit-page.mjs` sobre as rotas do namespace em `ui-inventory/routes.json` | tudo acima, agregado |
| Banco | `npm run agent:db-audit` | cascatas sensíveis, FKs anuláveis, legado, ordering, duplicidades |

## Severidade

| Nível | Critério | Exemplo |
|---|---|---|
| P0 | sistema quebrado | 5xx, página não abre |
| P1 | crítico | exceção JS, axe *critical*, dado errado em documento |
| P2 | importante | contraste AA, foco invisível, overflow, DEBUG padrão ligado |
| P3 | melhoria relevante | HTML pesado, DOM grande, duplicação, ciclo de import |
| P4 | refinamento | estilo inline, rota a confirmar |

Diferença estética pequena nunca é P0/P1. Axe: critical→P1, serious→P2, moderate→P3, minor→P4.

## Categorias

FUNCTIONAL · UX · VISUAL · ACCESSIBILITY · RESPONSIVE · PERFORMANCE · SECURITY · ARCHITECTURE · CONSISTENCY · MAINTAINABILITY
