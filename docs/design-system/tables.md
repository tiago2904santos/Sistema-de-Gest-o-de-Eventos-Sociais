# Tabelas e listas

**Hoje**: 53 tabelas no inventário (`ui-inventory/tables.json`); padrão de lista `components/v32/lista_registros.html`
(busca na barra, uma célula por registro no desktop, Data List no celular, paginação `paginacao.html`).

**Avaliação**: linha não clicável (UX-01); lista de prestações gera 656 KB de HTML (menus por linha);
`landmark-unique` repetido em listas com várias regiões iguais.

**Regra v4**: título da linha é link; ações secundárias num menu único reutilizado; cabeçalho com `scope="col"`;
wrapper com rolagem horizontal própria no celular (nunca a página); paginação no servidor; estado vazio e vazio-filtrado distintos.
