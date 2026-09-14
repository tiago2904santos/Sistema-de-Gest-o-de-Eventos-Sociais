# Servidor — cadastro

**Meta 0 aberta; observação parcial, sem certificação.** [Origem](imagens/meta0-servidor-form-origem.png), [destino](imagens/meta0-servidor-form-destino.png), [atributos dos campos](imagens/meta0-servidor-form-campos.json). Nenhum formulário enviado. As ausências abaixo não foram autorizadas.

**Correção após P04:** [formulário atual GV](imagens/meta1-servidor-form-origem.png)/[destino](imagens/meta1-servidor-form-destino.png). O destino agora usa template próprio, com campos explicitamente posicionados. O [ensaio de retorno](imagens/meta1-servidor-retorno-ensaio.json) confirmou que um nome fictício digitado foi restaurado após Gerenciar cargos e Voltar; depois foi apagado, sem envio.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Ordem | Nome, Cargo, CPF, RG, Telefone, Unidade | Mesma sequência | igual |
| Obrigatoriedade inicial | Só Nome obrigatório; demais opcionais | Só Nome obrigatório; demais opcionais | igual |
| Habilitação inicial | Os seis campos habilitados | Os seis campos habilitados | igual |
| CPF | Texto, limite 14, máscara CPF, exemplo `000.000.000-00` | Mesmos atributos observados | igual |
| RG | Limite 20, exemplo `00.000.000-0` | Limite 30; exemplo também oferece “NÃO POSSUI RG”. Contrato da origem ausente; mudança de validação não autorizada | ausente |
| Telefone | Limite 20; máscara telefone | Limite 16; máscara telefone. Limite da origem ausente; mudança não autorizada | ausente |
| Agrupamento | Identificação funcional: Nome a Telefone; Lotação: Unidade | Mesmos dois grupos; Nome ocupa duas colunas, Cargo uma, e CPF/RG/Telefone ficam na linha seguinte | igual |
| Pesquisa de Unidade | Sigla e nome completo nos resultados; texto escolhido exibe a sigla | Mesmos dados e apresentação observados em registros diferentes das duas bases | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Lista principal | Não integra a tela de cadastro | Não integra a tela de cadastro | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Gerenciar cargos e unidades: presença e destino | Links junto aos campos, preservando retorno ao cadastro | Links junto aos campos com retorno seguro à mesma página; retorno de Cargos com rascunho exercitado | igual |
| Ações do formulário | Voltar no cabeçalho e rodapé; Salvar | Mesmos textos e posições | igual |
| Escolher e retirar cargo | Menu oferece Selecione (opcional); escolha dessa opção deixa cargo vazio, inclusive após selecionar outro | Mesma opção e valor vazio observados após a correção do controle | igual |
| Buscar e escolher Unidade | Busca por nome sem acentos e sigla; Enter escolhe resultado destacado | Mesmos fluxos exercitados sem enviar cadastro | igual |
| Limpar Unidade | Limpar busca retira a seleção, fecha a lista e devolve foco à busca | Mesmo comportamento e valor nativo vazio | igual |
| Retorno com Unidade | Gerenciar unidades e Voltar ao servidor restauram a unidade selecionada | Mesma unidade restaurada no respectivo formulário; nomes e IDs pertencem a cada base | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Instrução inicial | “Só o nome é obrigatório; demais campos podem ser completados depois.” | Mesma mensagem | igual |
| Apoio dos grupos | “Dados pessoais e cargo”; “Unidade de lotação do servidor” | Mesmos textos nos grupos correspondentes | igual |
| Unidade sem resultado | Nenhuma unidade encontrada. | Mesma mensagem; Limpar busca disponível | igual |

O cargo padrão veio selecionado no GV e vazio aqui. Como os bancos e padrões diferem, isso **não comprova falha na regra de valor inicial**. A referência histórica a CPF obrigatório não corresponde à tela atual. Pendente: pesquisa e seleção, máscara ao digitar, edição, validação, persistência, retorno, mensagens após envio e permissões. Não alterar limites sem resolver a exigência de autorização da seção 9.

## Ensaio de respostas após P04

No destino, CPF inválido manteve o nome preenchido, mostrou “Corrija antes de continuar” e “Revise os campos destacados antes de continuar.” e levou o foco ao resumo, sem gravar. A mensagem global duplicada foi removida. [Registro do erro](imagens/meta1-servidor-erro-resumo-ensaio.json), [captura](imagens/meta1-servidor-erro-resumo-destino.png).

O servidor temporário foi salvo sem cargo/CPF com “Servidor salvo como rascunho. Complete cargo e CPF quando possível.”; ao receber cargo e CPF válido, exibiu “Servidor atualizado com sucesso.” e voltou à lista. [Rascunho](imagens/meta1-servidor-rascunho-resposta-ensaio.json), [atualização](imagens/meta1-servidor-atualizado-resposta-ensaio.json). O registro foi removido ao final. O retorno da edição ignora next, como no código da origem; a criação mantém retorno seguro. Os testes também cobrem criação completa. Nenhum POST foi enviado à origem, portanto os estados de resposta na origem continuam pendentes de prova visual e não ganham linha “igual”.

## Cargo opcional — comparação de seleção

A opção Selecione (opcional) existia no select nativo oculto do destino, mas faltava no menu visível. O componente ganhou a opção permitir_vazio, ativada somente para Cargo do formulário de servidor. Isso expõe uma possibilidade já aceita pelo formulário, sem alterar regra de obrigatoriedade, valores iniciais ou permissões. O comportamento padrão dos outros usos do componente permanece igual.

O ensaio no navegador abriu o menu, retirou a seleção inicial, escolheu um cargo existente e retirou a escolha novamente. Campo vazio e rótulo Selecione (opcional) foram confirmados nos dois lados. Os cargos escolhidos têm nomes diferentes porque as bases são distintas. Nenhum cadastro foi enviado neste ensaio de seleção; as entradas foram abandonadas por recarregamento. Isso não inclui a rodada anterior de grupos, cujo incidente está registrado separadamente.

Pares: [meta1-servidor-cargo-opcao-vazia](imagens/meta1-servidor-cargo-opcao-vazia-observacao.json), [meta1-servidor-cargo-vazio](imagens/meta1-servidor-cargo-vazio-observacao.json), [meta1-servidor-cargo-selecionado](imagens/meta1-servidor-cargo-selecionado-observacao.json), [meta1-servidor-cargo-retirado](imagens/meta1-servidor-cargo-retirado-observacao.json). [Valores efetivos](imagens/meta1-servidor-cargo-vazio-ensaio.json) e [validação](validacao-cargo-opcional.json). Quatro pares JPEG originais na galeria.

**Incidente anterior ainda aberto:** cargo34 ENSAIO DE CARGO foi criado indevidamente no GV durante a rodada de grupos; o cargo4 do destino foi removido. A limpeza na origem depende de P14. [Registro corrigido](incidente-cargo-origem.md). A presença desse cargo nas opções da origem não é dado de teste originalmente existente.


## Pesquisa de lotação — 10/09/2026

O seletor de Unidade usa o componente de seleção V3.2 com modo próprio de pesquisa de lotação. O nome completo passou a acompanhar a sigla nos resultados e a integrar a busca sem acentos. O botão Limpar busca retira a unidade; a lista fica fechada quando a pesquisa está vazia. Os demais seletores continuam usando seu controlador anterior. A obrigatoriedade, a validação dos identificadores e a gravação dos vínculos permanecem nas regras existentes.

No servidor foram exercitados foco inicial, busca pelo nome, Enter direto no primeiro resultado, busca sem resultado com Enter (sem envio), limpeza e retorno com a unidade selecionada. Limites das setas foram comparados no formulário de viatura; não constituem prova adicional no formulário de servidor.

Foram utilizadas ASCOM/ASCOM2 já existentes na origem e as unidades temporárias 100/101 do destino, ENSAIO LOTAÇÃO ALFA/BETA 20260910. As duas unidades temporárias foram removidas pelo catálogo e sua ausência confirmada no banco. Nenhum servidor ou viatura foi enviado; formulários abandonados por recarregamento. Nenhum POST foi enviado à origem nesta rodada. O incidente anterior P14 continua pendente.

Pares: [meta1-servidor-unidade-inicial](imagens/meta1-servidor-unidade-inicial-observacao.json), [meta1-servidor-unidade-busca](imagens/meta1-servidor-unidade-busca-observacao.json), [meta1-servidor-unidade-selecionada](imagens/meta1-servidor-unidade-selecionada-observacao.json), [meta1-servidor-unidade-sem-resultado](imagens/meta1-servidor-unidade-sem-resultado-observacao.json), [meta1-servidor-unidade-limpa](imagens/meta1-servidor-unidade-limpa-observacao.json), [meta1-servidor-unidade-retorno](imagens/meta1-servidor-unidade-retorno-observacao.json).

[Valores e limpeza](imagens/meta1-unidade-picker-ensaio.json). Os 142 testes de Cadastros passaram em PostgreSQL e SQLite; check e makemigrations limpos. A última suíte completa de 1.128 casos antecede este incremento. [Validação](validacao-unidade-picker.json). Metas abertas; edição com dados persistidos, perfis, responsividade e demais pendências anteriores não foram certificados nesta rodada.
