# Status

**Hoje**: chips com trio de tokens de estado (`ok/wn/dg/in/nt`), textos como "há 8 dias", "começa hoje",
"faltam 3 dias", "Justificativa pendente"; `lista_registros` risca linha cancelada.

**Regra v4**: um componente `status-chip` com mapa estado→(cor, ícone, rótulo) por domínio; nunca só cor;
datas relativas com `<time datetime>` (e o valor absoluto em `title`).
