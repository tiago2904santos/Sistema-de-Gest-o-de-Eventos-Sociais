# Meta 2 — Roteiros · Lista

**Origem:** `roteiros:index` (`/roteiros/`), em `templates/roteiros/index.html` e
`partials/_roteiro_linha.html`, alimentada por `roteiros/views.py::index`,
`roteiros/presenters.py::apresentar_linha_lista_simples_roteiro` e
`core/documento_abas.py`.
**Destino:** `viagens_roteiros:lista` (`/viagens/roteiros/`).
**Data:** 14/09/2026.

## Como esta comparação foi feita

A origem foi lida no código: rotas, view, presenter, regras das abas e os dois
templates. A tela do destino foi aberta no navegador contra o banco de
desenvolvimento, com dez roteiros reais.

**A origem não foi aberta no navegador.** Em 10/09/2026 uma comparação pela
interface gravou um cargo de ensaio no banco do Gerenciador de Viagens; desde
então a origem é tratada como leitura de código e consulta somente leitura ao
banco. Isso é desvio do protocolo da seção 6 das metas, e fica registrado como
tal: a evidência da origem aqui é o código que a produz, não a fotografia dela.

## Campos do filtro

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca `?q=` | servidor, placeholder "Buscar por sede, destino ou observações" | igual; procura sede, destino e observações | igual |
| Situação | multiescolha com as quatro abas, combináveis, contagem ao lado | igual, como caixas de seleção | igual |
| Sem situação marcada | mostra todos | mostra todos | igual |
| Limpar | botão, só quando há filtro | igual | igual |
| Contagem de resultados | no cabeçalho da listagem | "N roteiros" na barra | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Título da linha | rota: sede e destinos com unidade federativa | igual | igual |
| Volta à sede no título | não repete | não repete | igual |
| Selo | "faltam N dias", "falta 1 dia", "começa hoje", "em andamento", "foi hoje", "foi ontem", "há N dias" | mesmas palavras e limites | igual |
| Cancelado | prevalece sobre o selo temporal | igual | igual |
| Período | "dd/mm/aaaa a dd/mm/aaaa" | igual | igual |
| Trechos | "1 trecho" / "N trechos" | igual | igual |
| Valor | valor das diárias | igual, com o resumo abaixo | igual |
| Servidores | não exibido na linha | coluna própria | **adaptado**: a coluna já existia aqui e informa sem tirar nada |
| Ícone de tipo | não existe | distingue avulso de preso a uma solicitação | **adaptado**: o tipo não existe na origem |
| Composição | cartão por linha | tabela no desktop, Data List no celular | **adaptado**: pele do V3.2, mesma informação e mesmas ações |
| Paginação | sim | sim | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Novo roteiro | botão no cabeçalho | igual | igual |
| Editar na linha | ícone, com `?next=` preservando a volta | igual | igual |
| Excluir na linha | botão com diálogo de confirmação | igual, com confirmação e volta à lista filtrada | igual |
| Permissão de escrita | quem pode editar | igual; leitor não vê excluir nem "Novo roteiro" | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Lista vazia | mensagem própria | "Nenhum roteiro registrado ainda." | igual |
| Filtro sem resultado | "Ajuste a busca ou troque de aba." | "Nenhum roteiro com esses filtros. Ajuste a busca ou troque de situação." | igual |
| Sem data | roteiro entra em "Em andamento e realizados" | igual | igual |

## O que mudou no destino nesta meta

- Rota no título, com unidade federativa, no lugar de sede e destinos em colunas separadas.
- Período, contagem de trechos e valor na linha.
- Selo temporal com as palavras da origem.
- Quatro situações combináveis com contagem, no lugar de um menu de duas opções.
- Exclusão na própria linha, com confirmação, voltando à lista como estava.
- `?next=` no link de edição.
- Placeholder da busca corrigido: ele dizia "município" e a busca sempre cobriu
  sede, destino e observações.
- Mensagem de vazio distinguindo lista vazia de filtro sem resultado.

Onze testes novos cobrem o acima; a suíte do app passou de 119 para 130 casos.

## Pendências desta tela

Nenhuma. As diferenças remanescentes estão marcadas como adaptadas, com o motivo
na própria linha.
