# Meta 3 — Ofícios · Lista

**Origem:** `oficios:index` (`/oficios/`), cartão por ofício com filtros, situação, ordenação e dois períodos.
**Destino:** `viagens_oficios:lista` (`/viagens/oficios/`), em `pages/viagens_oficios/lista.html` e `_cartao.html`, alimentada por `viagens_oficios/views.py::lista`, `selectors.py`, `abas.py` e `presenters.py::cartao_da_lista`.
**Data:** 14/09/2026.

## Como esta comparação foi feita

A origem foi lida pelas capturas e pelas árvores acessíveis gravadas na Meta 0 em 10/09/2026 (`imagens/meta0-oficios-*-origem.png` e `meta0-oficios-*-observacao.json`): a lista inicial, o seletor de situação, o menu de ordenação, a ordenação aplicada (`?sort=numero_asc`), os dois calendários, a busca sem resultado e os quatro menus do cartão. A tela do destino foi aberta no navegador contra um banco de desenvolvimento com 26 ofícios de ensaio (viagem passada, futura, em andamento, cancelado, rascunho vazio, transporte manual, e vinte rascunhos para paginar).

**A origem não foi aberta no navegador nesta rodada:** este trabalho rodou num ambiente sem o Gerenciador de Viagens instalado. A evidência da origem é a fotografia de 10/09, não uma abertura nova. Fica registrado como desvio do protocolo da seção 6 das metas, do mesmo tipo do registrado na Meta 2.

Capturas do destino: [lista](imagens/meta3-oficios-lista-destino.png) ([antes](imagens/meta3-oficios-lista-antes.png)), [situação combinada](imagens/meta3-oficios-situacao-destino.png), [calendário da viagem](imagens/meta3-oficios-periodo-viagem-destino.png), [sem resultado](imagens/meta3-oficios-sem-resultado-destino.png), [celular](imagens/meta3-oficios-lista-celular-destino.png). Origem: [lista](imagens/meta0-oficios-origem.png), [situação](imagens/meta0-oficios-situacao-origem.png), [ordenação](imagens/meta0-oficios-ordenacao-origem.png), [calendário](imagens/meta0-oficios-periodo-viagem-origem.png), [sem resultado](imagens/meta0-oficios-sem-resultado-origem.png).

## Campos do filtro

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca `?q=` | nome acessível "Buscar ofícios", placeholder "Buscar por número, protocolo, motivo ou destino"; Enter envia | igual; procura número (`12` ou `12/2026`), protocolo com ou sem pontuação, motivo, destino do roteiro e nome de viajante | igual |
| Situação | combobox "Filtrar por situação" com quatro opções combináveis e contagem: Que vão acontecer, Em andamento e realizados, Finalizados, Cancelados | as quatro, com contagem, como caixas de seleção combináveis (`?situacao=`); sem nenhuma marcada, mostra todos | igual (mesma pele já aceita na Meta 2) |
| Ordenação | combobox "Número: maior" com Número: maior / menor, Criação: mais recente / mais antiga, Viagem: mais próxima / mais distante; `?sort=numero_asc` | as seis, mesmos rótulos e mesma chave `sort` (`numero_desc` é o padrão) | igual |
| Período da viagem | botão "Viagem" abre calendário com início e fim, mês, Hoje e Limpar; `viagem_de`/`viagem_ate` | calendário de intervalo do sistema, com Hoje e Limpar, nos mesmos parâmetros | igual |
| Período da criação | botão "Criação", calendário separado; `criacao_de`/`criacao_ate` | idem, calendário próprio | igual |
| Limpar | link "Limpar" que aparece com filtro aplicado | igual (aparece também quando a ordenação não é a padrão) | igual |
| Nome acessível dos dois calendários | os dois dizem "Filtrar por período da viagem" | "Viagem" e "Criação", cada um com o próprio nome | **adaptado**: a duplicidade da origem foi registrada na Meta 0 como defeito; aqui cada calendário diz o que filtra |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Contagem | "Mostrando **1–20** de **59**" com páginas "Ir para a página N" e setas, antes dos cartões | igual, 20 por página, `?page=`; repetida no rodapé quando há mais de uma página | igual (rodapé é acréscimo de pele) |
| Cabeçalho do cartão | "Nº 161/2026 · Protocolo 12.345.678-9"; abaixo "25/08 a 30/08/2026 · ALMIRANTE TAMANDARÉ/PR, ANTONINA/PR +1" | igual: período curto, destinos em maiúsculas com "+N" a partir do terceiro | igual |
| Selo | "há 11 dias", "faltam N dias", "falta 1 dia", "começa hoje", "em andamento", "foi hoje", "foi ontem"; sem data, "Rascunho" | mesmas palavras (selo temporal portado na Meta 2); Cancelado prevalece | igual |
| Equipe | lista com iniciais, nome, "CARGO · UNIDADE", marca "Motorista"; "Nenhum servidor informado" quando vazia | igual; a unidade usa a sigla quando tem | igual |
| Placa e modelo | blocos "Placa"/"Modelo" com "Não informado" em itálico quando vazios | igual; viatura cadastrada ou placa manual formatada | igual |
| Trechos | lista rolável "ORIGEM/PR → DESTINO/PR" e "dd/mm/aaaa HH:MM → dd/mm/aaaa HH:MM" | igual, na ordem dos trechos, horário local | igual |
| Valor | "Valor total", "R$ 4.358,25", valor por extenso, "Quantidade de diárias", "5 x 100%" | igual, pelo snapshot do efetivo do ofício (`diarias_para_servidores`) | igual |
| Justificativa | bloco "JU · Justificativa · Preenchida/Pendente" com o texto ou "Nenhuma justificativa informada." | igual, texto abreviado em 160 caracteres | igual |
| Composição | cartão escuro com blocos internos | cartão claro do V3.2 com os mesmos blocos; no celular, blocos empilhados | **adaptado**: pele |
| Cancelado | não observado na Meta 0 | título riscado, selo "Cancelado", fundo suave; menus de documento escondidos e "Reativar ofício" no lugar de cancelar | **adaptado**: sem fotografia da origem para o caso |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Novo ofício | botão de formulário POST (cria o rascunho e abre o editor), no cabeçalho e no estado sem resultado | igual: `POST viagens_oficios:criar` reserva o número e abre o editor | igual (antes era um link GET para o formulário vazio) |
| Editar ofício | ícone de lápis no rodapé do cartão, para `dados-viajantes` | lápis para o formulário, com `?next=` preservando a volta à lista filtrada | igual |
| Documentos do ofício | pasta no rodapé: Visualizar ofício, Baixar PDF, Baixar DOCX | mesmos itens e descrições; ver [oficios-menus.md](oficios-menus.md) | igual |
| Mais ações | Retificar ofício, Ofício complementar, Cancelar ofício, Excluir ofício | mesmos itens e descrições; a ação volta para a lista como estava | igual |
| Termo por pessoa | menu junto ao nome: Visualizar termo, Baixar PDF, Baixar DOCX, Anexar assinado | igual | igual |
| Justificativa | lápis "Editar justificativa" e pasta "Abrir documentos da justificativa" | igual; o lápis abre o formulário na etapa da justificativa | igual |
| "Resumo" | não existe no cartão (o resumo é uma etapa do wizard) | link "Resumo" no rodapé, para a tela de conferência | **adaptado**: aqui as etapas 5 e 6 do wizard são uma tela própria; o cartão precisa de um caminho até ela |
| Permissão | quem edita vê as ações | leitor vê os cartões e "Abrir"; sem menus, sem "Novo ofício" | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Sem resultado | título "Nenhum ofício", "Nenhum ofício encontrado com os filtros aplicados.", botão Novo ofício | igual | igual |
| Lista vazia sem filtro | não observado | "Nenhum ofício" / "Nenhum ofício registrado ainda." | **adaptado**: sem fotografia da origem para o caso |
| Equipe e transporte vazios | "Nenhum servidor informado"; "Não informado" | igual | igual |
| Justificativa pendente | "Pendente"; "Nenhuma justificativa informada." | igual | igual |
| Retorno das ações | não observado (não foram acionadas na origem) | mensagem de sucesso com o número do ofício; exclusão bloqueada por vínculo avisa e não apaga | **adaptado**: textos daqui |

## O que mudou no destino nesta meta

- Tabela de seis colunas com "Abrir" virou o cartão da origem, com equipe, transporte, trechos, valor e justificativa.
- Filtros de status/ano/fila viraram busca, quatro situações combináveis com contagem, seis ordenações e dois períodos com calendário; `?page=` e "Mostrando 1–20 de N".
- Quatro menus de ação por cartão, com os mesmos itens e descrições da origem.
- "Novo ofício" passou a ser POST que cria o rascunho numerado e abre o editor, como lá.
- As ações de retificar, complementar, cancelar, reativar e excluir aceitam `?next=` e voltam para onde foram disparadas; retificar e complementar ligam e desligam a marca.
- `viagens_oficios/abas.py` porta as quatro situações (`core/documento_abas.py` da origem) com a saída do ofício vinda do roteiro ou do primeiro trecho.

Prova: `viagens_oficios/tests/test_paridade_meta3.py` (lista, ações, formulário, detalhe e catálogos) e a suíte dos apps de viagens verde.
