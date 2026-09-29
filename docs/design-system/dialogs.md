# Diálogos

**Hoje**: 34 diálogos (`ui-inventory/dialogs.json`), a maioria `<dialog>` nativo (`dialogo_baixar`, `dialogo_assinado`,
`andamento_modal` — este sem uso).

**Regra v4**: `<dialog>` nativo com `showModal()`, `aria-labelledby`, foco inicial no primeiro controle, Esc fecha,
foco volta ao gatilho, `shadow.4`/`z.dialog`; destrutivo com botão de confirmação explícito.
