# Ofícios — lista, filtros e ordenação

**Meta 0 aberta; observação parcial, sem certificação.** Inspeção em 10/09/2026 com GV na área 1 e destino autenticado. [Lista inicial GV](imagens/meta0-oficios-origem.png)/[Eventos](imagens/meta0-oficios-destino.png). Complementos reais: [situação GV](imagens/meta0-oficios-situacao-origem.png)/[Eventos](imagens/meta0-oficios-situacao-destino.png), [ordenação GV](imagens/meta0-oficios-ordenacao-origem.png)/[Eventos](imagens/meta0-oficios-ordenacao-destino.png), [ordenação aplicada GV](imagens/meta0-oficios-ordenacao-aplicada-origem.png)/[Eventos](imagens/meta0-oficios-ordenacao-aplicada-destino.png).

Também foram registrados [calendário Viagem GV](imagens/meta0-oficios-periodo-viagem-origem.png)/[Eventos](imagens/meta0-oficios-periodo-viagem-destino.png), [calendário Criação GV](imagens/meta0-oficios-periodo-criacao-origem.png)/[Eventos](imagens/meta0-oficios-periodo-criacao-destino.png), [busca vazia GV](imagens/meta0-oficios-sem-resultado-origem.png)/[Eventos](imagens/meta0-oficios-sem-resultado-destino.png), [contraparte GV do filtro Fila](imagens/meta0-oficios-fila-destino-origem.png)/[Fila no destino](imagens/meta0-oficios-fila-destino-destino.png). As capturas de calendário e menus usam o enquadramento visível da janela; o conteúdo acessível completo está nos respectivos arquivos `-observacao.json`.

Todas as ausências abaixo são pendências **sem autorização de dispensa**. Quantidades e números de ofício diferentes pertencem a bases distintas, não demonstram falha de migração nesta tarefa.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca: estado | Campo textual inicialmente vazio; mantém o termo depois de aplicar | Mesmo estado inicial e preservação do termo observado | igual |
| Identificação da busca | Nome acessível “Buscar ofícios”; exemplo visual menciona número e protocolo | Rótulo “Busca”; identificação original ausente, sem autorização | ausente |
| Situação | Seletor com múltipla seleção subjacente: Que vão acontecer (0), Em andamento e realizados (56), Finalizados (0), Cancelados (3) | Situação: Rascunho, Gerado, Finalizado (legado), Arquivado. Fila separada: Ativos, Cancelados, Todos. Composição e opções originais ausentes; sem autorização para mudar regras | ausente |
| Ordenação | Número: maior; Número: menor; Criação: mais recente; Criação: mais antiga; Viagem: mais próxima; Viagem: mais distante | Sem controle correspondente; ausência não autorizada | ausente |
| Período da viagem | Botão visual Viagem abre calendário com início/fim, mês, Hoje e Limpar | Sem intervalo correspondente; ausência não autorizada | ausente |
| Período da criação | Botão visual Criação abre calendário separado | Sem intervalo correspondente; ausência não autorizada | ausente |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Identificação por documento | Número/ano, protocolo quando preenchido, situação ou indicação temporal | Número/ano, data, protocolo e situação na tabela | igual |
| Equipe | Nomes, cargo, unidade e indicação de motorista; menu de termo por pessoa | Quantidade de viajantes; detalhes de equipe e menu por pessoa ausentes nesta lista, sem autorização | ausente |
| Transporte e percurso | Placa, modelo, trechos com origem/destino, datas e horários | Não exibidos na lista; ausência não autorizada | ausente |
| Valores | Total, valor por extenso e composição da quantidade de diárias | Não exibidos na lista; ausência não autorizada | ausente |
| Justificativa | Situação Preenchida/Pendente, texto e ações | Bloco não exibido na lista; ausência não autorizada | ausente |
| Aplicação da ordenação observada | Selecionar Número: menor mudou o controle; Enter na busca enviou GET com `sort=numero_asc` e a lista passou a começar por 01/2026, 02/2026, 03/2026 | Sem controle para reproduzir essa sequência; ausência não autorizada | ausente |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Aplicar busca | Enter no campo envia os filtros; exercitado sem gravação | Botão Filtrar envia os filtros; exercitado sem gravação | igual |
| Limpar filtros | Link Limpar após aplicar; exercitado restaurando lista | Link correspondente não exibido; para restaurar foi necessário apagar o termo e Filtrar. Ausência não autorizada | ausente |
| Ações por documento | Editar ofício, documentos, mais ações, justificativa e termos | Apenas Abrir na linha; acessos diretos originais ausentes, sem autorização | ausente |
| Novo ofício: presença | Botão Novo ofício, inclusive no estado sem resultado | Link Novo ofício, inclusive no estado sem resultado | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Busca sem resultado | “Nenhum ofício”; “Nenhum ofício encontrado com os filtros aplicados.” | “Nenhum ofício encontrado.” Textos originais ausentes; sem autorização | ausente |
| Justificativa pendente | “Justificativa Pendente”; “Nenhuma justificativa informada.” | Bloco não exibido na lista; ausência não autorizada | ausente |
| Equipe e transporte vazios | “Nenhum servidor informado”; “Não informado” em placa e modelo | Esses dados não compõem a lista atual; mensagens ausentes, sem autorização | ausente |

O GV mostrou 59 ofícios, 20 por página e navegação antes dos cartões. O destino mostrou dois registros, insuficientes para comprovar sua paginação. Não foi observado seletor de tamanho de página nesta inspeção; a menção do pedido continua como requisito a conferir, sem inventar uma captura desse controle.

Os dois calendários têm nomes acessíveis iguais (“Filtrar por período da viagem”), embora os botões visuais sejam Viagem e Criação e abram painéis diferentes. A duplicidade foi registrada, sem decisão de descartar ou alterar comportamento da origem. Nenhuma data nem situação foi selecionada. O ensaio de ordenação descreve o que ocorreu; não afirma que Enter seja o único mecanismo possível de aplicação.

O botão Novo ofício da origem pertence a formulário POST. Não foi acionado, preservando o banco da origem. Pendente: criação em contexto autorizado, filtros positivos/combinados, múltipla seleção, calendários selecionados, todas as ordenações, paginação e tamanho de página, permissões e estados de erro/carregamento. Menus detalhados em [oficios-menus.md](oficios-menus.md). A Meta 3 não foi iniciada.
