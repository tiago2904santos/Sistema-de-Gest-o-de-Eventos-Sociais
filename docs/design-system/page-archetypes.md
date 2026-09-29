# Arquétipos de página

| Arquétipo | Estrutura | Exemplos | Regras |
|---|---|---|---|
| LIST | cabeçalho + filas + busca/filtros + lista + paginação + ação flutuante | ofícios, prestações, publicações | linha clicável; vazio e vazio-filtrado; exportar respeita filtros |
| FORM | trilha + cabeçalho + seções numeradas + barra de ações fixa | nova solicitação, ofício | autosave de rascunho quando longo; resumo de erros; sair sem salvar avisa |
| DETAIL | trilha + cabeçalho com status + blocos + histórico | detalhe da solicitação | ações conforme permissão; histórico recolhível |
| DASHBOARD | cabeçalho + KPIs (`summary_card`) + blocos | hub, dashboard | KPI clicável leva à lista filtrada |
| WIZARD | etapas com progresso | prestação (diário → RT → documentos → PDF) | etapa atual anunciada; voltar sem perder dados |
| CALENDAR | filtros + calendário | agenda | dias da semana corretos (BUG-01); navegável por teclado |
| DOCUMENT | editor/visualizador + ações de geração | editor de documentos, PDF | geração com estado de carregando e erro de motor |
| SETTINGS | trilho lateral de seções + formulário | cadastros, configurações | salvar por seção |
| SEARCH | busca + resultados | busca de municípios/servidores | debounce; vazio orientativo |
| REPORT | filtros de período + tabela/gráfico + exportar | relatórios | período na URL |
| EMPTY | ilustração/ícone + texto + ação | listas vazias | diz o que fazer a seguir |
| ERROR | identidade + mensagem + caminho de volta | 403/404/500 | sem detalhes técnicos em produção |
| AUTH | cartão central + marca | login, troca de senha | autocomplete correto; mostrar senha |

O arquétipo de cada página-chave está em `tests/support/pages.ts`.
