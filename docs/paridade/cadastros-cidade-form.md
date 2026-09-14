# Cidade e município — inclusão

**Meta 0 aberta; observação parcial, sem certificação.** [Inclusão rápida no GV](imagens/meta0-cidade-form-origem.png), [diálogo no destino](imagens/meta0-cidade-form-destino.png), [atributos](imagens/meta0-cidade-form-campos.json). Inspeção em 10/09/2026 sem preencher ou enviar dados. Ausências não autorizadas.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Nome: estado inicial | Texto obrigatório, vazio e habilitado | Mesmo tipo, obrigatoriedade e estado inicial | igual |
| Nome: limite e exemplo | Limite 255, sem placeholder; atributo de maiúsculas | Sem maxlength no controle observado, exemplo “Ex.: Curitiba”. Atributos originais ausentes; sem autorização para alterar validação | ausente |
| Estado | Segundo campo, seleção obrigatória, habilitada e vazia | Segundo campo, seleção obrigatória, habilitada e vazia | igual |
| Capital | Terceiro campo; árvore acessível expõe interruptor opcional desligado. Captura mostra o rótulo, mas não distingue visualmente o interruptor | Campo Região obrigatório em seu lugar; controle Capital ausente, sem autorização | ausente |
| Codigo ibge | Numérico opcional, vazio e habilitado, após Capital | Não exibido; ausência sem autorização | ausente |
| Latitude e Longitude | Numéricos opcionais, vazios e habilitados, nessa ordem | Não exibidos; ausência sem autorização | ausente |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Contexto de inclusão | Região expandida dentro da lista, com cartões e paginação | Diálogo sobre a lista; região de inclusão original ausente, sem autorização | ausente |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Fechar sem gravar | Cadastrar cidade recolhe região; exercitado | Fechar cadastro fecha diálogo; exercitado | igual |
| Abrir inclusão | “Cadastrar cidade” | “Novo município”. Redação original ausente; sem autorização | ausente |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Nome acessível da região de inclusão | “Dados da cidade — Nome e estado” na árvore acessível; não aparece como título visual na captura | Diálogo chamado “Novo município”; nome acessível original ausente, sem autorização | ausente |

O destino oferece Cancelar e Salvar município e informa “Informe os dados do município que poderão ser utilizados nas solicitações.” Não apareceu botão de envio na inclusão rápida do GV; não se inferiu salvamento por Enter nem automático. Pendente: envio e validações, visibilidade e acionamento do interruptor Capital, máscaras ao digitar, opções e pesquisa de Estado, relação Capital/Região e permissões. O atributo HTML ausente não prova ausência de validação no servidor. Mudança de campos, regras ou permissões em produção requer a decisão prevista na seção 9; esta ficha apenas registra a diferença, sem implementar alteração. A rota de criação direta da origem não foi exercitada: a evidência mostra sua inclusão rápida na listagem.

## Decisão P13 e nova consulta

A lista foi alinhada separadamente em `/viagens/cadastros/cidades/`, sem implementar inclusão provisória com regras diferentes. A comparação de inclusão acima continua histórica, referente ao diálogo administrativo de Eventos. P13 aguarda autorização para Nome255, Região opcional e coordenadas informáveis; o modelo compartilhado mantém Nome150, Região obrigatória e seus vínculos existentes. O cadastro rápido continua ausente na nova consulta, sem autorização para dispensá-lo.
