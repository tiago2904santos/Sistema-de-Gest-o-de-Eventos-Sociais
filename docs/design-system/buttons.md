# Botões

**Hoje**: `components/v32/button.html` — variantes `primario` (`.btn-primaria`), `secundario` (`.btn--secundaria`),
`perigo` (`.btn--destrutiva`), `fantasma` (`.btn--quieta`); vira `<a>` com `href`. Botão flutuante `.btn-flutuante`
para a ação principal das listas. Muitas telas ainda usam classes do V2 (`.btn`, `.btn--dourado`).

**Estados no UI Lab**: default, hover, focus, conteúdo longo. **Faltam**: disabled e loading no componente.

**Regra v4**: uma ação primária por região; destrutiva sempre com confirmação; `loading` com `aria-busy` e rótulo mantido;
foco visível; alvo ≥ 44px no celular.
