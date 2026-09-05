repo: tiago2904santos/Sistema-de-Gest-o-de-Eventos-Sociais
branch: main

## Last sync
date: 2026-09-04T16:24:20Z

### Updated in this project
- Etapa 1: diagnóstico visual global e arquitetura do Design System (documento de análise).
- Etapa 2a: fundamentos consolidados em `design-system/tokens.css` + `design-system/components.css`.
- Etapa 2b: página-piloto "Solicitações de Eventos Sociais — lista" com todos os estados.
- Etapa 2c (V2): recomposição da piloto — shell em duas faixas, trilha vertical de filas, toolbar coesa, tabela sem grade (`design-system/components-v2.css`).
- Etapa 2d (V3): composição editorial em folha única, filas horizontais, tabela sem moldura, ícones Lucide reais de `templates/components/icon.html` e brasão de `static/icons/favicon.svg`; painel de Tweaks com densidade, divisórias e presença do dourado (`design-system/components-v3.css`).
- Etapa 2e (V3.1): art direction sobre a V3 — neutros reaquecidos (matiz ~40°), dourado tratado como bronze, cabeçalho unificado com resumo operacional, toolbar única tonalizada, filas como navegação com aba ativa, tabela refinada com cabeçalho fixo (`design-system/components-v3-1.css`).
- Etapa 2f (V3.2 — versão vigente): direção da referência aprovada pelo usuário — controles de busca/filtro/ferramenta contornados e arredondados, tabela em painel com cabeçalho tonalizado, indicadores operacionais com ícone no cabeçalho, chevron + kebab sempre visíveis na linha e ação de workflow sempre à vista (`design-system/components-v3-2.css` + `piloto-v3-2.js`). Botão primário em dourado sólido, sem degradê. Painel de filtros sem rodapé e sem a linha de metainformação: chips de filtro ativo e "Limpar" vivem na toolbar.
- A tentativa V3.3 (art direction adicional) foi descartada pelo usuário e removida do projeto.
- Etapa 3 (padrão oficial): a V3.2 foi aprovada como referência-base de todas as listagens do sistema. Composição, hierarquia, densidade, tabela, toolbar, filas, ações por linha, paginação e estilo institucional desta tela não devem ser reinterpretados nas demais páginas de listagem — apenas adaptados aos dados de cada uma.
- Estados derivados criados em `Padrao de Listagem - Estados.html` (reaproveita `piloto-v3-2.js` + `design-system/components-v3-2.css`, sem nova direção visual): normal, filtros avançados abertos, vazio sem registros, sem resultados de busca, hover de linha, menu de ações aberto, ordenação ativa, mobile (via container query `.pagina{container-type:inline-size}`, sem @media).
- Etapa 4 (mobile): `Padrao de Listagem - Mobile.html` + `piloto-mobile.js` — composição mobile própria (app shell, seletor de módulo com drawer, KPIs em faixa, tab scroller de filas, Data List, bottom sheets de Filtros e Ordenar, paginação compacta) com 7 estados. A abordagem anterior de container query (desktop espremido) foi descartada.
- Etapa 5 (documentação): `Padrao de Listagem - Contratos e Variantes.html` — contratos responsivos, variantes, ações por status, estados e tokens da família.
- Etapa 6 (detalhe, refeito com base no formulário real): `Piloto - Detalhe da Solicitacao 216.html` — estado Aguardando despacho. Seções e campos espelham `templates/pages/solicitacoes/form.html` (1 Dados da solicitação, 2 Solicitante, 3 Serviços e estrutura do evento, 4 Planejamento operacional, 5 Anexos, 6 Despacho da DG, 7 Histórico) e `solicitacoes/forms.py` (SolicitacaoForm.Meta.fields, DespachoForm, campos condicionais de unidade móvel/motorista). Timeline lateral vem de `services.py :: montar_timeline`; resumo lateral de `templates/components/solicitation_summary.html`. A versão anterior, que inventava "Recursos solicitados" e protocolo, foi descartada.
- Etapa 7 (congelamento): `Piloto - Detalhe da Solicitacao 216.html` — estado Aguardando despacho aprovado como **padrão oficial de Detalhe / Workflow**. Composição congelada: 4 regiões principais (Resumo da solicitação, Serviços e estrutura, Planejamento operacional, Decisão da Diretoria-Geral) + sidebar sticky contínua (Acompanhamento, Resumo operacional, Anexos, Histórico). Apenas microajustes de espaçamento/alinhamento nesta etapa — sem mudança de componentes ou fluxo.
- Etapa 8 (Nova Solicitação): `Piloto - Nova Solicitacao (desktop).html` — formulário contínuo (sem cards numerados) sobre o mesmo Design System. Seções e campos vêm de `templates/pages/solicitacoes/form.html` + `solicitacoes/forms.py` (SolicitacaoForm.Meta.fields, campos condicionais de unidade móvel/motorista). Sem autosave — confirmado que não existe no repositório. Componentes novos: checkbox card de serviços, stepper numérico de equipes, sidebar com Resumo + stepper vertical de etapas.
- Etapa 9 (mobile do formulário + painel): `Piloto - Nova Solicitacao Mobile.html` e `... (validacao erros).html` — app shell mobile aprovado, coluna única, stepper horizontal, resumo recolhível, action bar sticky com safe area. `Piloto - Painel Eventos Sociais (desktop).html` — painel operacional novo (não existia painel para o módulo: só `demandas_eventos/views.py :: dashboard` e `coffee_break/views.py :: painel`), seguindo o padrão daquele dashboard (4 KPIs com link para a lista filtrada + lista de próximos eventos). Métricas dos contadores de fila de `solicitacoes/views.py` (FILAS + `Count(filter=)`); série mensal e tempo médio até decisão das views SQL de relatório (`0010_simplifica_views_powerbi`: `vw_solicitacoes.mes_evento`, `vw_tempos_workflow.dias_envio_ate_decisao`); distribuição por `DecisaoDG`.
- Etapa 10 (Cadastros): `Piloto - Cadastros (desktop).html` — os 6 cadastros de apoio de `cadastros/views.py :: CADASTROS` (tipos-evento, servicos, equipes, orgaos, municipios, unidades-moveis) viraram trilha lateral com contadores; a lista à direita usa a Data Table aprovada, com busca por nome, filtro Ativos/Inativos, 20 por página e ações Editar / Alternar ativo / Excluir de `cadastros/urls.py`. Colunas de Municípios (nome, estado, região) de `cadastros/models.py`. A página consolida `index.html` + `lista.html` numa única tela para eliminar espaço desperdiçado.
- Nenhuma alteração de código no repositório: regras de negócio, colunas, filtros, ações e status preservados.

## Congelados
- Piloto V3.2 - Solicitacoes (desktop).html — Listagem, desktop
- Padrao de Listagem - Mobile.html — Listagem, mobile
- Piloto - Detalhe da Solicitacao 216.html — Detalhe/Workflow, Aguardando despacho, desktop

## Screen map
| Entrega no projeto | Arquivos de origem |
| --- | --- |
| Diagnóstico e Design System (análise) | `static/css/design-system.css`, `static/css/viagens-cadastros.css`, `templates/layouts/*`, `templates/components/*`, `templates/pages/*`, `auditoria-visual/NOTAS-VISUAIS.md`, `docs/auditoria-visual-2026-09-02/` |
| Fundamentos do Design System | `static/css/design-system.css` (tokens, seções 1–16 e apêndices) |
| Piloto — Solicitações (lista) | `templates/pages/solicitacoes/lista.html`, `solicitacoes/views.py` (FILAS, ORDENACOES, `_colunas_ordenaveis`, `_queryset_filtrado`), `solicitacoes/models.py` (StatusSolicitacao, DecisaoDG), `templates/components/{status_badge,select,input,page_header,breadcrumb,icon}.html` |
| Padrão de Listagem — Estados (desktop) | mesmas origens da piloto de lista |
| Padrão de Listagem — Mobile | mesmas origens da piloto de lista (mesmo contrato de dados, composição mobile) |
| Contratos e Variantes (documentação) | `solicitacoes/views.py`, `solicitacoes/models.py`, `templates/pages/solicitacoes/lista.html` |
| Piloto — Cadastros | `cadastros/views.py` (CADASTROS, `lista`, filtros q/situacao, ITENS_POR_PAGINA), `cadastros/models.py` (CadastroBase, Municipio, Estado, Regiao), `cadastros/urls.py` (novo/editar/alternar_ativo/excluir), `templates/pages/cadastros/{index,lista}.html` |
| Piloto — Painel Eventos Sociais | `solicitacoes/views.py` (FILAS, agregações `Count(filter=)`), `solicitacoes/migrations/0010_simplifica_views_powerbi.py` (`vw_solicitacoes`, `vw_tempos_workflow`), `solicitacoes/models.py` (StatusSolicitacao, DecisaoDG), `demandas_eventos/views.py :: dashboard` (padrão de painel do produto) |
| Piloto — Detalhe da Solicitação #216 | `templates/pages/solicitacoes/form.html` (seções 1–7 e fieldsets), `solicitacoes/forms.py` (SolicitacaoForm, DespachoForm, AnexoForm), `solicitacoes/models.py`, `solicitacoes/services.py` (TRANSICOES_VALIDAS, CAMPOS_OBRIGATORIOS_ENVIO, montar_timeline), `solicitacoes/urls.py`, `templates/components/solicitation_summary.html` |
