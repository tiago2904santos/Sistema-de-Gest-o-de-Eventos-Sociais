# Cidades — lista, paginação e busca

**Metas 0 e 1 abertas. Correção parcial por P04; sem certificação completa.** Comparação autenticada em 10/09/2026, área 1 na origem. A consulta de Viagens agora usa `/viagens/cadastros/cidades/`, sobre a base compartilhada de municípios. O cadastro administrativo de Eventos continua disponível em sua rota anterior.

Pares atuais: [lista](imagens/meta1-cidades-lista-observacao.json), [página 2](imagens/meta1-cidades-pagina2-observacao.json), [nome sem acento](imagens/meta1-cidades-busca-nome-observacao.json), [UF](imagens/meta1-cidades-busca-uf-observacao.json), [nome estadual](imagens/meta1-cidades-busca-estado-observacao.json), [busca paginada](imagens/meta1-cidades-busca-pagina2-observacao.json), [sem resultado](imagens/meta1-cidades-sem-resultado-observacao.json) e [limpeza](imagens/meta1-cidades-limpar-observacao.json). Cada registro acompanha dois JPEGs originais, visíveis lado a lado na [galeria](imagens/comparacao-inicial.html#meta1-cidades-lista). Capturas `meta0` preservam a tabela anterior.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca | Texto; Buscar cidades; vazio na abertura e termo mantido após pesquisar | Mesmo tipo, rótulo e estados observados | igual |
| Digitação e foco | cambe consulta automaticamente sem Enter; foco permanece na busca | Mesmo comportamento, com o campo de busca do DS V3.2 | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Composição | Cartões com iniciais, nome e linha UF · IBGE; travessão se IBGE ausente | Mesmos elementos, usando componentes e classes V3.2 | adaptado — pele autorizada na seção 2 |
| Página inicial e segunda página | 15 itens; régua antes dos cartões; 1–15 e 16–30 | Mesmas faixas e posição; totais próprios da base | igual |
| Busca pelo nome sem acento | cambe encontra CAMBÉ; não mantém page=2 | cambe encontra Cambé; não mantém page=2 | igual |
| Busca estadual | pr e parana encontram cidades pelo estado, além de correspondências textuais no nome | Mesma pesquisa por nome/UF/estado; resultados adicionais de outras UFs pertencem à base nacional | igual |
| Paginação filtrada | Página 2 conserva q=parana | Mesmo termo conservado na página 2 | igual |
| Página única | Régua ausente com o resultado de cambe | Régua ausente com o resultado de cambe | igual |
| Ordem | Cidades observadas em sequência alfabética dentro de PR | Sequência por sigla de UF e nome; base observada abrange várias UFs | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Limpar | Remove busca e página; restaura a lista inicial | Mesmo resultado exercitado | igual |
| Navegar | Número 2 abre a segunda página, inclusive após pesquisar | Mesmo comportamento exercitado | igual |
| Ações por cidade | Nenhuma nos cartões observados | Nenhuma nos cartões da consulta de Viagens; administração de Eventos mantém suas ações na rota própria | igual |
| Cadastrar cidade | Expande inclusão na lista | Inclusão ainda ausente nesta rota; regras de Nome, Região e coordenadas aguardam P13, sem dispensa autorizada | ausente |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca sem resultado | Nenhum registro cadastrado; Nenhuma cidade cadastrada ainda. | Mesmas duas mensagens com ZZZ_PARIDADE_SEM_RESULTADO | igual |
| Recuperar lista vazia por filtro | Limpar mantém caminho para lista completa | Mesmo texto e recuperação exercitados | igual |

O GV contém 49 cidades; o destino, 5.571 municípios, incluindo códigos IBGE que não estão preenchidos nos registros comparados da origem. Diferenças de valores, caixa dos nomes e quantidade pertencem aos bancos; os dados não foram reescritos. As consultas observadas foram apenas GET. Não houve gravação na base de desenvolvimento nesta rodada.

Pendências: inclusão e validações P13; autorização/perfis da origem ainda não comparados; responsividade, carregamento e erro. A permissão administrativa existente de Municípios foi preservada na consulta e no CSV, além da barreira do módulo Viagens. Isso não certifica equivalência de permissões. A ordenação entre diferentes UFs não pôde ser pareada porque a origem observada contém somente PR.

Exportação: `/viagens/cadastros/cidades/exportar.csv` implementada com BOM UTF-8, cabeçalho Cidade/UF e base inteira ordenada, ignorando q/page como a view do GV. A origem não apresenta link de exportação nos cartões ou cabeçalho observados; nenhum botão foi inventado. Contrato validado por teste com aspas/vírgulas e acesso administrativo. Download real pareado ainda pendente: não é prova visual certificada.

Validação: quatro testes novos de consulta, paginação, permissão/ausência de gravação e CSV. Suíte de cadastros com 142 testes aprovada em PostgreSQL e SQLite. Check e makemigrations limpos. A última suíte completa de 1.124 testes antecede esta alteração e não a certifica; ver [registro atual](validacao-cidades.json).

Conferência final de atributos: o tipo da busca foi alinhado de search para text, como no GV. As oito capturas foram renovadas após esse ajuste; a busca cambe foi repetida sem Enter e preservou o foco nos dois lados. [Atributos reais](imagens/meta1-cidades-busca-atributos.json).
