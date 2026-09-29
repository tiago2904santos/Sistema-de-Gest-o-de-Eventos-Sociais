# Elevação

| Nível | Uso | Sombra | z-index |
|---|---|---|---|
| 0 | página, painéis | nenhuma (borda `neutral.200`) | base |
| 1 | cartões destacados, cabeçalho fixo | `shadow.1` | `z.sticky`/`z.header` |
| 2 | menus, popovers, selects abertos | `shadow.2` | `z.dropdown` |
| 3 | painéis flutuantes, drawers | `shadow.3` | `z.overlay` |
| 4 | diálogos modais | `shadow.4` | `z.dialog` |
| — | toasts | `shadow.2` | `z.toast` |

**Hoje**: z-index de 1 a 110 sem escala (60, 61, 62, 100, 110 competem). Regra v4: só `tokens/z-index.json`.
