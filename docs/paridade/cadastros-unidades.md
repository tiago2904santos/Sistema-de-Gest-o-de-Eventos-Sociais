# Unidades — lista e inclusão rápida

**Meta 0 aberta; Meta 1 em andamento por P04. Observação parcial, sem certificação.** Comparação em 10/09/2026, GV na área 1 e destino na porta 8021. O cartão do destino usou um registro temporário, removido ao final.

Pares na [galeria lado a lado](imagens/comparacao-inicial.html): `meta1-unidade-inclusao`, `meta1-unidades-cartoes-ensaio`, `meta1-unidades-busca-sigla`, `meta1-unidades-sem-resultado`, `meta1-unidade-confirmacao`, `meta1-unidades-retorno-servidor`. Cada nome corresponde a imagens `-origem.png` e `-destino.png` e ao registro `-observacao.json`. [Atributos dos campos](imagens/meta1-unidade-form-campos.json).

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Nome | Texto obrigatório, limite 255, vazio e habilitado, sem exemplo | Mesmos atributos na inclusão rápida | igual |
| Sigla | Texto opcional, limite 50, vazio e habilitado, sem exemplo | Mesmos atributos na inclusão rápida | igual |
| Ordem e composição | Nome e Sigla lado a lado, com larguras iguais na captura; título do grupo disponível à acessibilidade | Mesma ordem, Nome mais largo e apresentação do bloco visível, componentes do DS V3.2 | adaptado — composição visual do DS V3.2, autorizada na seção 2 |
| Inclusão dentro da lista | Somente Nome e Sigla | Mesmos campos, sem laço genérico de formulário | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Identificação | Cartão com iniciais da sigla, nome e sigla abaixo | Mesmas informações, observadas com unidade de ensaio | adaptado — cartões do DS V3.2; bases distintas |
| Busca por sigla | Buscar unidades; 10DP encontra 10º DISTRITO POLICIAL | Mesmo rótulo; epu01 encontra a unidade EPU01 | igual |
| Limpar | Link ao lado da busca preenchida, remove o termo | Mesmo controle e resultado observado | igual |
| Busca automática por nome sem acento | Digitar subdivisao encontra SUBDIVISÃO, sem Enter | Digitar paginacao encontra PAGINAÇÃO nos registros temporários, sem Enter | igual |
| Paginação | 97 itens, 15 por página; páginas 1, 4 e 7 observadas, limites desabilitados | Mesma régua e contagem com 97 registros temporários; busca mantida ao avançar | igual |
| Ações visíveis por cartão | Editar e Excluir | Mesmas ações visíveis; comportamento da edição pendente abaixo | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Cadastrar unidade | Expande região dentro da lista | Expande a inclusão rápida com campos próprios | igual |
| Edição inline | Botão Editar no cartão preenche o painel, segundo código e inventário anterior | Ainda abre formulário completo com gerenciamento de lotação; fluxo inline ausente, sem autorização para dispensá-lo | ausente |
| Excluir | Abre diálogo com nome, avisos, Voltar e Excluir | Mesmos textos e controles no diálogo do DS V3.2 | adaptado — pele autorizada na seção 2 |
| Voltar no diálogo | Fecha sem remover o registro | Mesmo resultado observado com o registro temporário | igual |
| Retorno ao servidor | Link Voltar ao servidor depois da lista quando há next | Mesmo texto e posição; endereço de retorno validado | igual |
| Abrir pelo teclado | Botão Excluir acionado por Space abre a confirmação e foca Voltar | Mesmo comportamento observado | igual |
| Circular o foco | Shift+Tab de Voltar leva a Excluir; Tab de Excluir leva a Voltar | Mesmo ciclo observado, corrigido para não perder foco fora do diálogo | igual |
| Cancelar pelo teclado | Escape fecha a confirmação sem envio | Mesmo fechamento observado sem envio | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Apoio da inclusão | Dados da unidade — Nome e sigla nomeia o grupo acessível, sem título ou subtítulo visível | Mesmo grupo acessível, sem acrescentar os textos à superfície visual | igual |
| Busca sem resultado | Nenhum registro cadastrado / Nenhuma unidade cadastrada ainda. | Mesmas palavras após zzsemresultado | igual |
| Aviso de exclusão | Você está prestes a excluir [nome]. Se houver vínculos com outros registros, a exclusão será bloqueada. | Mesmas palavras, com o nome do registro local | igual |
| Irreversibilidade | Esta ação é permanente e não poderá ser desfeita. | Mesmas palavras | igual |

Ensaios de escrita realizados **somente no destino**: criação de ENSAIO PARIDADE UNIDADES 20260910 01 (id 1, sigla EPU01), tentativa duplicada rejeitada mantendo Nome/Sigla, cancelamento e exclusão do registro temporário. Mensagens observadas: Unidade criada com sucesso.; Já existe uma unidade com este nome.; Unidade excluída com sucesso. A origem não recebeu POST, portanto equivalência dos resultados de escrita não está certificada. Evidências: [duplicidade](imagens/meta1-unidade-duplicidade-ensaio.json), [cancelamento](imagens/meta1-unidade-cancelamento-ensaio.json), [limpeza](imagens/meta1-unidade-limpeza-ensaio.json).

Retorno: o destino conservou Modelo da viatura e Nome do servidor após Gerenciar unidades/Voltar. No GV, os cliques no atalho não permaneceram na lista neste ensaio; o catálogo com next foi aberto diretamente para verificar o link de volta. Ao voltar dessa abertura direta, o Nome estava vazio. O [par de formulários de viatura](imagens/meta1-unidades-retorno-viatura-observacao.json) registra apenas os valores visíveis, não prova uma ida e volta completa da origem. [Observação e limite](imagens/meta1-unidades-retornos-ensaio.json). Investigar antes de certificar ou inferir adaptação.

Pendente: edição inline e rota direta de criação; decisões sobre a interface de lotação hoje existente; teclado completo e estados sem permissão/bloqueio no navegador; retorno com cadastro efetivamente criado; normalização durante digitação e mensagens de erro comparadas integralmente. A lista do GV apresentou 97 unidades e 15 cartões na primeira página; o destino voltou a ficar vazio após limpeza. Nenhuma ausência dispensada.

Validação técnica parcial: **116 testes de cadastros aprovados em PostgreSQL e SQLite**, incluindo busca por nome/sigla sem acentos, paginação, duplicidade, retorno seguro, auditoria, permissões e garantia de que inclusão rápida não move servidores. O formulário completo e sua atualização de lotação permanecem disponíveis, com os testes anteriores preservados. Check e makemigrations limpos. A suíte completa anterior (1.088 testes) antecede os incrementos de viaturas/unidades e não fecha esta meta. [Validação](validacao-unidades.json).

## Conferência de busca e paginação

O destino agora espera um segundo sem digitação para enviar a busca GET e restaura foco/cursor. Pares reais: `meta1-unidades-busca-automatica`, `meta1-unidades-busca-nome-sem-acento`, `meta1-unidades-paginacao-primeira`, `meta1-unidades-paginacao-intermediaria`, `meta1-unidades-paginacao-ultima` e `meta1-unidades-paginacao-com-busca`. Consultados na galeria e nos registros de observação correspondentes. A navegação com busca foi exercitada pelo link Próxima página nos dois lados. A busca iniciada na página 4 retornou à primeira página do resultado.

Foram criadas 97 unidades fictícias exclusivamente para visualizar a paginação do destino. Todas removidas após conferir identidade e ausência de vínculos: [manifesto](../../logs/paridade-unidades-paginacao-fixtures.json). Nenhum dado da origem alterado. A edição rápida que preserva lotação aguarda P06; o restante dessa tela permanece parcial. Validação mais recente em `validacao-cadastros-busca.json`; os 116 testes acima são do incremento anterior.

Validação atual desta rodada: 117 testes de cadastros e 1.103 testes completos por banco, aprovados (quatro dispensas no PostgreSQL; cinco no SQLite). [Logs e limitações](validacao-cadastros-busca.json). Substitui os resultados anteriores como evidência técnica atual, sem certificar a meta.

## Teclado das confirmações após P04 — 10/09/2026

Comparação real: o destino antes deixava o foco sair do diálogo ao usar Shift+Tab em Voltar; o GV o levava ao botão Excluir. O ciclo foi alinhado. A ação da lista agora usa botão, como a origem, permitindo abertura por Space. O envio continua no botão Excluir dentro da confirmação, com a mesma URL, permissões e regras da view.

Pares: [meta1-unidades-exclusao-teclado](imagens/meta1-unidades-exclusao-teclado-observacao.json), [meta1-unidades-exclusao-ciclo-foco](imagens/meta1-unidades-exclusao-ciclo-foco-observacao.json). [Sequência de teclas e foco](imagens/meta1-dialogos-teclado-ensaio.json); [validação](validacao-dialogos.json). Capturas JPEG originais, sem edição, na galeria.

Somente no destino, três registros temporários foram criados e removidos para exercitar as listas vazias: combustível 4, unidade 99 e viatura 3 (ZZT9T91). Nenhum servidor foi vinculado. Ausência desses registros confirmada no banco. Os demais registros foram apenas usados para abrir e cancelar diálogos. Nenhum POST na origem. Sucesso e bloqueios após POST da origem continuam pendentes; a comparação do teclado não os certifica.

## Composição e busca conferidas em 10/09/2026

A classificação anterior dos títulos de apoio era imprecisa: a origem usa essas palavras apenas no nome acessível do grupo. O destino agora faz o mesmo, com fieldset nomeado e campos explícitos; os títulos visuais adicionais foram removidos. Capturas anteriores permanecem históricas. Foram conferidos campo vazio e preenchido, ordem, tipo, obrigatoriedade, limites e transformação em maiúsculas. A comparação real dos atributos resultou igual nos três grupos. Isso não certifica os resultados após POST. [Atributos](imagens/meta1-grupos-cadastro-atributos.json).

A busca usa type=text como no GV. O rótulo e o exemplo coincidem; zzgrupo20260910 foi digitado sem Enter nas duas telas. A consulta automática manteve termo e foco e mostrou as mensagens sem resultado. [Atributos e URLs reais](imagens/meta1-cadastros-busca-tipos-depois.json).

Pares atuais: [meta1-unidades-grupo-acessivel](imagens/meta1-unidades-grupo-acessivel-observacao.json), [meta1-unidades-grupo-preenchido](imagens/meta1-unidades-grupo-preenchido-observacao.json), [meta1-unidades-busca-texto](imagens/meta1-unidades-busca-texto-observacao.json). JPEGs originais na [galeria](imagens/comparacao-inicial.html#meta1-unidades-grupo-acessivel). A declaração anterior de nenhuma gravação foi corrigida: o ensaio de cargo criou o registro34 na origem e o registro4 no destino. Ver incidente abaixo.

Validação: sete templates compilados; check e makemigrations limpos; campos e buscas exercitados no navegador. A suíte de 142 testes por banco aprovada na rodada de diálogos antecede este ajuste de apresentação e não foi repetida. As metas e as demais pendências continuam abertas. [Registro](validacao-grupos-cadastros.json).

## Correção do relato da rodada de grupos

A rodada gravou indevidamente ENSAIO DE CARGO no GV (cargo34, área1) e no destino (cargo4). O registro do destino foi removido; a remoção na origem aguarda P14. As capturas e os atributos observados permanecem evidências dos estados mostrados, mas a rodada não cumpriu a restrição de origem somente leitura. [Registro completo e prevenção](incidente-cargo-origem.md). Nenhuma meta pode ser certificada com base na declaração anterior de ausência de gravação.
