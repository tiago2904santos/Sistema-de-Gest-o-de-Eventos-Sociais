# Viatura — formulário próprio

**Metas 0 e 1 abertas. Correção parcial sob P04; nenhuma diferença dispensada.**

Pares: [formulário GV](imagens/meta1-viatura-form-origem.png)/[Eventos](imagens/meta1-viatura-form-destino.png), [busca GV](imagens/meta1-viatura-motoristas-busca-origem.png)/[Eventos](imagens/meta1-viatura-motoristas-busca-destino.png), [seleção GV](imagens/meta1-viatura-motorista-selecionado-origem.png)/[Eventos](imagens/meta1-viatura-motorista-selecionado-destino.png), [sem resultado GV](imagens/meta1-viatura-motoristas-sem-resultado-origem.png)/[Eventos](imagens/meta1-viatura-motoristas-sem-resultado-destino.png). [Atributos](imagens/meta1-viatura-form-campos.json). As capturas anteriores `meta0-*` permanecem como histórico.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Ordem | Placa, Modelo, Tipo, Combustivel, Unidade (opcional), Motoristas | Mesma ordem e rótulos visíveis | igual |
| Obrigatoriedade | Só Placa obrigatória | Só Placa obrigatória | igual |
| Exemplo da placa | AAA1234 ou AAA1A23 | Mesmo texto | igual |
| Limite e máscara da placa | Limite 7; máscara retira separadores | Limite 10 e máscara anterior do destino conservados. Comportamento original ainda ausente, sem autorização para alterar validação | ausente |
| Modelo | Opcional, limite 120, sem exemplo e vazio | Mesmos atributos | igual |
| Tipo inicial | Descaracterizada | Descaracterizada | igual |
| Unidade inicial | Opcional, sem seleção, Buscar unidade | Mesmos atributos observados | igual |
| Pesquisa de motoristas | Digite nome, cargo ou CPF | Mesmo texto; busca por nome exercitada nos dois lados | igual |
| Blocos | Identificação com quatro campos; Lotação; Motoristas | Mesma composição com componentes e classes V3.2, conforme seção 2 | adaptado |
| Pesquisa de Unidade | Sigla e nome completo nos resultados; texto escolhido exibe a sigla | Mesmos dados e apresentação observados em registros diferentes das duas bases | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Resultado de motorista | Nome, iniciais, cargo/unidade quando existentes | Resultado em menu com os dados disponíveis, em componentes V3.2 permitidos pela seção 2 | adaptado |
| Selecionado | Cartão com nome, indicação Motorista, dados complementares e remoção | Mesma composição; bases têm pessoas e vínculos diferentes | igual |
| Lista principal de viaturas | Não integra o cadastro | Não integra o cadastro | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Gerenciar combustíveis, unidades e servidores | Links próximos dos controles, com retorno na URL | Mesmos links junto aos controles, com destinos equivalentes | igual |
| Selecionar motorista | Clique no resultado ou Enter cria cartão e limpa busca | Ambos exercitados; duas seleções por teclado sem duplicatas | igual |
| Navegar nos resultados | Primeiro destacado ao digitar; setas com limites, Escape fecha e seta reabre | Mesma sequência observada após correção | igual |
| Remover motorista | Botão Remover com nome da pessoa | Mesmo comportamento exercitado sem envio | igual |
| Retirar combustível | Selecione (opcional) deixa o valor vazio, inclusive após escolher um combustível | Mesma sequência e valor vazio confirmados | igual |
| Opções de Tipo | Caracterizada e Descaracterizada, sem opção vazia no menu observado | Mesmas duas opções; Caracterizada selecionada no ensaio | igual |
| Ações finais | Voltar e Salvar | Voltar e Salvar | igual |
| Buscar e escolher Unidade | Busca por nome sem acentos e sigla; Enter escolhe resultado destacado | Mesmos fluxos exercitados sem enviar cadastro | igual |
| Limpar Unidade | Limpar busca retira a seleção, fecha a lista e devolve foco à busca | Mesmo comportamento e valor nativo vazio | igual |
| Retorno com Unidade | Gerenciar unidades e Voltar ao servidor restauram a unidade selecionada | Mesma unidade restaurada no respectivo formulário; nomes e IDs pertencem a cada base | igual |
| Teclado de Unidade | Setas param nos extremos; Escape fecha e seta reabre preservando a pesquisa | Limites e sequência repetidos nos dois sistemas | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Instrução inicial | Só a placa é obrigatória; demais campos podem ser completados depois. | Mesmas palavras no cabeçalho e painel | igual |
| Apoio de motoristas | Servidores autorizados a conduzir | Mesmas palavras | igual |
| Sem seleção | Nenhum motorista selecionado. | Mesmas palavras | igual |
| Busca sem resultado | Nenhum motorista encontrado. | Mesmas palavras | igual |
| Cadastro incompleto na seleção | Rascunho no resultado e no cartão selecionado | Mesma indicação, usando o status existente; selo V3.2 conforme seção 2 | adaptado |
| Unidade sem resultado | Nenhuma unidade encontrada. | Mesma mensagem; Limpar busca disponível | igual |

O formulário de domínio agora tem blocos explícitos; não usa o renderizador genérico de campos. A seleção envia somente os identificadores dos motoristas escolhidos e conserva a validação do ModelForm. Valores de placa e demais regras de produção foram mantidos. A diferença de placa continua pendente; não foi considerada uma adaptação autorizada.

Ensaios adicionais **somente no destino**: seleção por teclado; envio de placa inválida, sem criar viatura, preservando motorista selecionado; ida e volta pelos três links de gerenciamento. Placa, modelo e seleção foram preservados. Evidências: [retorno por combustível](imagens/meta1-viatura-retorno-ensaio.json), [retornos por servidores e unidades](imagens/meta1-viatura-retornos-adicionais-ensaio.json), [erro](imagens/meta1-viatura-erro-ensaio.json) e [captura de erro](imagens/meta1-viatura-erro-ensaio.png). Nenhum formulário de viatura foi salvo com sucesso no banco de desenvolvimento neste incremento. Os campos temporários foram abandonados por navegação para o formulário vazio; o rascunho de retorno já havia sido consumido. A origem não recebeu POST.

Pendências: decisão sobre limite/máscara da placa; comparação de edição e gravação; ensaio pareado de RG/unidade; retorno com alteração real nos catálogos; estados de erro/permissão nos dois lados; comportamento em telas estreitas. Combustível padrão selecionado na origem e vazio no destino decorre das respectivas configurações; a regra de sugestão do destino foi preservada e testada, sem equiparar as bases.

Validação: 111 testes de cadastros em cada banco, todos aprovados; check e makemigrations limpos. A última suíte completa registrada, de 1.088 testes, antecede este incremento. Nenhuma meta foi encerrada.


## Busca e teclado do seletor de motoristas

Sete novos pares, com capturas da área visível e DOM completo: `meta1-viatura-motoristas-cargo`, `meta1-viatura-motoristas-reabrir-seta`, `meta1-viatura-motoristas-limite-superior`, `meta1-viatura-motoristas-multiplos-teclado`, `meta1-viatura-motoristas-remocao-parcial`, `meta1-viatura-motoristas-cpf-sem-mascara` e `meta1-viatura-motoristas-cpf-formatado`. Disponíveis na [galeria](imagens/comparacao-inicial.html#meta1-viatura-motoristas-cargo).

A busca agora destaca o primeiro resultado ao digitar. Escape fecha o menu; a seta para baixo reabre e avança ao segundo. A seta para cima para no primeiro, como observado no GV. O destino antes circulava nos extremos e deixava o menu fechado após Escape. Enter seleciona; os cartões seguem a ordem de cadastro, selecionados não reaparecem na busca e remover um mantém o outro. Nenhum formulário foi enviado; recarregar abandonou as seleções nos dois lados.

A busca textual foi alinhada aos dados da origem: nome, cargo, CPF e RG formatados, sigla e nome completo da unidade. CPF completo sem pontuação não encontrou resultado no GV; o destino passou a reproduzir esse comportamento, sem alteração dos valores gravados ou da validação do cadastro. RG e nome completo de unidade foram exercitados no GV e em teste isolado no destino, ainda sem par visual com dados correspondentes. [Ensaios adicionais](imagens/meta1-viatura-motoristas-ensaios.json).

O resultado sem cargo/unidade agora apresenta “Servidor cadastrado”, conforme o componente da origem. Esse estado foi visto apenas no destino nesta rodada; não fica certificado por leitura de código. O selo Rascunho e o limite inferior com vários resultados foram identificados como pendências nesta rodada e tratados no complemento abaixo. Perfis e demais estados não exercitados continuam pendentes.

Validação deste incremento: 132 testes de Cadastros por banco, todos aprovados; check, makemigrations e sintaxe JavaScript limpos. A suíte completa anterior, com 1.111 testes por banco, antecede este incremento e a consulta de CEP. [Registro atual](validacao-motoristas.json). Metas 0 e 1 abertas.


## Selo Rascunho e limite inferior — complemento

O resultado da busca e o cartão escolhido agora apresentam Rascunho quando esse é o status gravado no servidor. A regra que calcula o status não foi alterada. A indicação Motorista permanece antes de Rascunho no cartão; dados complementares só ocupam espaço quando existem. Foi reaproveitado o selo V3.2 usado na lista de servidores.

Cinco pares novos: `meta1-viatura-motoristas-rascunho-opcao`, `meta1-viatura-motoristas-rascunho-cartao`, `meta1-viatura-motoristas-rascunho-retorno`, `meta1-viatura-motoristas-rascunho-removido` e `meta1-viatura-motoristas-limite-inferior`. [Galeria](imagens/comparacao-inicial.html#meta1-viatura-motoristas-rascunho-opcao). O selo permaneceu ao restaurar a seleção e foi removido com o cartão; ao remover o último, ambos exibiram Nenhum motorista selecionado. Duas listas com dois resultados foram percorridas com três setas para baixo; o destaque permaneceu no segundo resultado em ambas.

O ensaio de retorno tem um limite: o destino ofereceu Voltar à viatura no catálogo de servidores, mas a origem não mostrou um link de retorno nessa navegação. O formulário da origem foi reaberto diretamente e restaurou a seleção. Isso comprova restauração e apresentação do selo nesse estado, sem certificar os caminhos de retorno como equivalentes. A causa da ausência do link na origem não foi determinada e nenhuma diferença de navegação foi dispensada.

Nenhum formulário foi enviado; os cadastros usados já existiam. As seleções foram abandonadas por recarregamento. Verificação técnica proporcional: os 10 testes existentes de viaturas passaram em PostgreSQL e SQLite; check e makemigrations limpos. Não foram adicionados testes para esta alteração de apresentação. A última execução ampla de Cadastros (132 por banco) antecede somente este complemento; a suíte completa de 1.111 por banco também antecede CEP e os ajustes de busca. [Validação do complemento](validacao-motoristas-rascunho.json). Metas abertas.


## Decisão P11 sobre o caminho de retorno

A diferença investigada no retorno pelo catálogo de servidores agora tem autorização: o usuário decidiu preservar o botão Voltar à viatura e o caminho mantido na criação/busca do destino. A view do GV prepara o retorno, mas o template de servidores não o expõe ou repassa nessas ações. P11 cobre essa adaptação, sem certificar outras navegações. O ensaio do destino criou e removeu somente o servidor temporário 8 e verificou o retorno à viatura. [Detalhes](validacao-servidores-retorno.json).

## Seletores de combustível e tipo — 10/09/2026

O menu de Combustível agora expõe Selecione (opcional), já aceita pelo campo do formulário. Foi ativada a opção permitir_vazio do componente somente nesse controle. O seletor de Tipo foi conferido e preservado: o GV oferece apenas Caracterizada e Descaracterizada, embora o campo não esteja marcado como obrigatório. Não foi inventada uma opção vazia para Tipo.

Foi exercitada a sequência combustível vazio, escolha e retirada. O valor nativo ficou vazio novamente, sem enviar a viatura. A origem usou DIESEL; o destino usou o combustível temporário5 ENSAIO SELETOR COMBUSTIVEL 20260910, criado e removido somente no destino. A ausência do temporário foi confirmada no banco. Os formulários de viatura foram abandonados por recarregamento. Nenhum cadastro da origem foi enviado neste ensaio; o incidente anterior do cargo34 continua separado e pendente de P14.

Pares: [meta1-viatura-combustivel-opcao-vazia](imagens/meta1-viatura-combustivel-opcao-vazia-observacao.json), [meta1-viatura-combustivel-vazio](imagens/meta1-viatura-combustivel-vazio-observacao.json), [meta1-viatura-combustivel-selecionado](imagens/meta1-viatura-combustivel-selecionado-observacao.json), [meta1-viatura-combustivel-retirado](imagens/meta1-viatura-combustivel-retirado-observacao.json), [meta1-viatura-tipo-opcoes](imagens/meta1-viatura-tipo-opcoes-observacao.json), [meta1-viatura-tipo-caracterizada](imagens/meta1-viatura-tipo-caracterizada-observacao.json). [Valores efetivos](imagens/meta1-viatura-seletores-opcionais-ensaio.json) e [limpeza no destino](imagens/meta1-viatura-combustivel-limpeza-seletor.json). [Validação técnica desta rodada](validacao-seletores-viatura.json). Todas as demais pendências da ficha permanecem abertas.

Validação após este incremento: suíte completa de 1.128 testes aprovada em PostgreSQL (quatro pulados) e SQLite (cinco pulados); check e makemigrations limpos. Limitações do ambiente e registros completos em [validacao-seletores-viatura.json](validacao-seletores-viatura.json). Nenhuma meta encerrada.


## Pesquisa de lotação — 10/09/2026

O seletor de Unidade usa o componente de seleção V3.2 com modo próprio de pesquisa de lotação. O nome completo passou a acompanhar a sigla nos resultados e a integrar a busca sem acentos. O botão Limpar busca retira a unidade; a lista fica fechada quando a pesquisa está vazia. Os demais seletores continuam usando seu controlador anterior. A obrigatoriedade, a validação dos identificadores e a gravação dos vínculos permanecem nas regras existentes.

O ensaio cobriu nome sem acentos, sigla, clique, Enter, setas com limites, Escape/reabertura e retorno pelo catálogo. Ao pesquisar depois de selecionar, o valor nativo anterior permanece até escolher outro ou usar Limpar busca, comportamento observado nos dois lados. O link do catálogo se chama Voltar ao servidor mesmo ao retornar à viatura nos dois sistemas; esse texto foi preservado.

Foram utilizadas ASCOM/ASCOM2 já existentes na origem e as unidades temporárias 100/101 do destino, ENSAIO LOTAÇÃO ALFA/BETA 20260910. As duas unidades temporárias foram removidas pelo catálogo e sua ausência confirmada no banco. Nenhum servidor ou viatura foi enviado; formulários abandonados por recarregamento. Nenhum POST foi enviado à origem nesta rodada. O incidente anterior P14 continua pendente.

Pares: [meta1-unidade-busca-antes](imagens/meta1-unidade-busca-antes-observacao.json), [meta1-unidade-sem-resultado](imagens/meta1-unidade-sem-resultado-observacao.json), [meta1-unidade-limpa](imagens/meta1-unidade-limpa-observacao.json), [meta1-unidade-nome-sem-acento](imagens/meta1-unidade-nome-sem-acento-observacao.json), [meta1-unidade-limite-inferior](imagens/meta1-unidade-limite-inferior-observacao.json), [meta1-unidade-selecao-teclado](imagens/meta1-unidade-selecao-teclado-observacao.json), [meta1-unidade-busca-sigla](imagens/meta1-unidade-busca-sigla-observacao.json), [meta1-unidade-limite-superior](imagens/meta1-unidade-limite-superior-observacao.json), [meta1-unidade-escape](imagens/meta1-unidade-escape-observacao.json), [meta1-unidade-reaberta](imagens/meta1-unidade-reaberta-observacao.json), [meta1-unidade-selecao-clique](imagens/meta1-unidade-selecao-clique-observacao.json), [meta1-unidade-retorno-viatura](imagens/meta1-unidade-retorno-viatura-observacao.json), [meta1-unidade-retirada](imagens/meta1-unidade-retirada-observacao.json).

[Valores e limpeza](imagens/meta1-unidade-picker-ensaio.json). Os 142 testes de Cadastros passaram em PostgreSQL e SQLite; check e makemigrations limpos. A última suíte completa de 1.128 casos antecede este incremento. [Validação](validacao-unidade-picker.json). Metas abertas; edição com dados persistidos, perfis, responsividade e demais pendências anteriores não foram certificados nesta rodada.
