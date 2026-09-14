# Diárias — vigências e cadastro

Meta 0 aberta; Meta 1 parcial após P04. [Inclusão e histórico na origem](imagens/meta1-diarias-inclusao-historico-origem.png)/[destino](imagens/meta1-diarias-inclusao-historico-destino.png), [histórico e ações na origem](imagens/meta1-diarias-historico-acoes-origem.png)/[destino](imagens/meta1-diarias-historico-acoes-destino.png). As capturas desta rodada cobrem áreas visíveis; a captura de página inteira falhou, e as observações JSON contêm o DOM completo. Os pares `meta0-*` permanecem como histórico.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Faixa | Obrigatória, vazia; Interior, Capital, Brasília | Mesmos valores e ordem, usando select DS V3.2 | adaptado — controle exigido na seção 7 |
| Data | Rótulos “Vigência a partir de” e “Vigente a partir de”; calendário do sistema | Mesmos dois rótulos e exibição somente leitura; campo oculto preenchido em ISO aqui, vazio no ensaio da origem | adaptado — componentes DS exigidos na seção 7; equivalência do campo oculto pendente de P09 |
| Diária de 24 horas | Numérico obrigatório, vazio, passo 0,01, sem placeholder | Mesmos atributos de apresentação e ordem | igual |
| Mínimo | Entrada aceita a partir de 0,01; POST não ensaiado | Mantido mínimo 0,04 para derivados positivos | ausente — equivalência pendente de P08; nenhuma dispensa recebida |
| Campo oculto da data após selecionar | Vazio, apesar da data exibida; repetido após recarregar | Preenchido com a data ISO | ausente — equivalência não comprovada; P09 pendente, sem dispensa |
| Percentuais iniciais | Campos vazios, desabilitados e somente leitura, “15% (calculado)” e “30% (calculado)” | Mesmos atributos e rótulos | igual |
| Prévia ao digitar 290,55 | R$ 43,58 e R$ 87,17 | Mesmos valores observados | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Composição | Nova vigência seguida de histórico na mesma superfície | Nova vigência e histórico reunidos, com blocos próprios | igual |
| Colunas | Faixa, Vigente a partir de, 24 horas, 15%, 30% | Mesmas cinco colunas e ordem | igual |
| Ordenação | Mais recente primeiro; faixa desempata | Mesma ordem; datas diferem entre as bases | igual |
| Valores monetários | R$ com duas casas e vírgula | Mesma apresentação | igual |
| Abas da configuração | Instituição, Ofício, Roteiros | Integração ainda pendente | ausente — sem autorização de dispensa |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Ações finais | Voltar e Salvar após o histórico | Mesmos textos e posição | igual |
| Voltar | Aponta ao início | Aponta ao início | igual |
| Calendário | Abre controle próprio; seleção de 10/09/2026 ensaiada | Abre pelo campo ou botão; mesma data selecionada | adaptado — componente exigido na seção 7; par meta1-diarias-data-selecionada |
| Permissão de alterar | Somente superusuário, conforme código | Permissões atuais preservadas, incluindo VIAGENS_GESTOR | adaptado — decisão P02; perfis ainda não comparados no navegador |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Explicação da prévia | “Prévia do cálculo. Os percentuais não são editáveis e são gravados pelo servidor a partir do valor de 24 horas.” | Mesmas palavras junto de 30% | igual |
| Histórico | “Vigências cadastradas”; “Da mais recente para a mais antiga”; “Histórico de valores por faixa.” | Mesmos textos | igual |
| Nova vigência | “Um valor de 24h; 15% e 30% são derivados no servidor” | Mesmo texto | igual |
| Ajuda principal | Explica os percentuais, a data de vigência e a preservação dos valores anteriores | Mesma redação observada | igual |

Pares adicionais: `meta1-diarias-previa-calculada`, `meta1-diarias-calendarios`, `meta1-diarias-data-selecionada`. Correção da observação anterior: o campo do GV é **somente leitura**, confirmado no DOM; a afirmação anterior de que permitia digitar era incorreta. Antes deste incremento, o DS começava no domingo e incluía salto anual. O modo GV optativo corrigiu semana, rótulos, controles e abertura pelo campo; os demais calendários continuam no modo padrão.

A antiga coluna Ações e os cartões de valores vigentes foram retirados da composição para reproduzir as cinco colunas do GV. Os endpoints existentes de edição/exclusão e suas permissões permanecem, sem mudança das regras em produção. A rota antiga de inclusão agora usa a mesma superfície de formulário e histórico. Esses endereços adicionais não certificam uma rota da origem.

No destino, 0,01 foi recusado pela validação do navegador antes do envio, com “Informe um número maior.”, mantendo os campos. [Ensaio](imagens/meta1-diarias-erro-ensaio.json). A duplicidade de Interior em 01/01/2026 foi enviada ao servidor e recusada, preservando data, faixa, valor e histórico; foco foi ao resumo. O resumo exibiu a explicação explícita de duplicidade e também a mensagem de unicidade do modelo. [Ensaio](imagens/meta1-diarias-duplicidade-ensaio.json). Nenhum POST foi enviado à origem; as respectivas mensagens continuam sem certificação comparada.

As três vigências de desenvolvimento ficaram intactas; nenhum valor de diária foi criado ou atualizado neste ensaio. [Conferência dos dados](ensaio-diarias-dados-preservados.json). Criação, derivação a partir do valor-base, preservação da vigência anterior, duplicidade e POST recusado a operador foram exercitados em banco de teste isolado. A mensagem somente leitura menciona os perfis autorizados, adaptada por P02. Estados vazio/somente leitura e gravação bem-sucedida ainda não foram comparados em navegador. Validação técnica atual: 125 testes de cadastros por banco; a última suíte completa de 1.108 antecede esta rodada.

## Calendário — conferência do comportamento

O modo optativo do componente DS foi ativado somente no campo de vigência. Foram comparados abertura por clique no campo, foco pelo teclado, mês anterior e seguinte, seleção de data anterior e de dia fora do mês visível, Hoje, Limpar, Escape e clique externo. A grade de agosto teve as mesmas 42 datas, de 27/07/2026 a 06/09/2026. Limpar apagou a seleção, voltou ao mês atual e manteve o painel aberto nos dois sistemas. Escape fechou os dois painéis e devolveu o foco a “Abrir calendario”. Selecionar 01/11/2026 pela grade de outubro mostrou a mesma data e fechou os dois painéis. A inspeção dos campos ocultos, porém, encontrou uma divergência: destino 2026-11-01; origem vazia. A seleção por Hoje foi repetida após recarregar a origem e a divergência persistiu (exibição 10/09/2026, campo oculto vazio). Nenhum POST foi enviado. P09 solicita decisão para preservar o envio correto do destino; a equivalência do valor de envio não está certificada.

Pares: `meta1-diarias-calendario-campo`, `meta1-diarias-calendario-mes-anterior`, `meta1-diarias-calendario-data-retroativa`, `meta1-diarias-calendario-limpar`, `meta1-diarias-calendario-hoje`, `meta1-diarias-calendario-teclado`, `meta1-diarias-calendario-mes-seguinte`. Registros: [grade](imagens/meta1-diarias-calendario-grade-ensaio.json), [atributos e seleção](imagens/meta1-diarias-calendario-atributos.json), [fechamento](imagens/meta1-diarias-calendario-fechamento-ensaio.json).

O calendário padrão foi exercitado no formulário de solicitação: continua iniciando no domingo, com saltos anuais; seleção e limpeza funcionaram, e Limpar fechou o painel como antes. [Regressão](imagens/meta1-calendario-padrao-regressao.json). Nenhum formulário foi enviado neste incremento. Os ensaios não certificam todos os tamanhos de tela ou tecnologias assistivas. Abas, perfis comparados e demais pendências da meta permanecem abertas. Resultados técnicos em `validacao-calendario-diarias.json`.

**Retificação de alcance:** as comparações anteriores de seleção certificam apenas a data visível e os controles exercitados. Não comprovam que o GV enviaria a data escolhida. O código atual da origem prevê preencher o oculto, mas o comportamento observado no navegador foi diferente; a causa não foi determinada e a origem não foi modificada.
