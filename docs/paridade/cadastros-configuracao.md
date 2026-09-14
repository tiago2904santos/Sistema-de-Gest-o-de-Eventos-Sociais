# Configuração — Instituição e Ofício

**Meta 0 aberta; observação parcial, sem certificação. P01 pendente.** [Instituição GV](imagens/meta0-configuracao-instituicao-origem.png)/[Eventos](imagens/meta0-configuracao-instituicao-destino.png); [Ofício GV](imagens/meta0-configuracao-oficio-origem.png)/[Eventos](imagens/meta0-configuracao-oficio-destino.png). A contraparte atual é o formulário institucional de Eventos; seu catálogo separado de assinantes não foi conferido neste par. Nenhum formulário enviado.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Bloco de endereço | Unidade, CEP, Número, Logradouro, Bairro, Cidade, UF, E-mail, Telefone, Ramal | Misturado a sede, prazo e destinatário; outra ordem, com número após UF. Composição original ausente, sem autorização | ausente |
| UF apresentada | Nome do estado em controle de leitura | Campo UF editável. Regra visual da origem ausente; alteração de regra não autorizada | ausente |
| Destinatário: dados disponíveis | Nome, Cargo, Unidade lotada | Nome, Cargo e Unidade do destinatário | igual |
| Assinantes de Ofício e Justificativa | Seletores na aba Ofício | Não estão nesta tela; link para catálogo separado. Composição original ausente, sem autorização | ausente |
| Assinantes de Plano de Trabalho e Ordem de Serviço | Dois seletores em Demais assinantes | Não exibidos. **P01: usuário manteve a decisão pendente; omissão não autorizada** | ausente |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Abas | Instituição, Ofício, Roteiros | Formulário único; abas ausentes, sem autorização | ausente |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Salvar: presença | Botão Salvar | Botão Salvar | igual |
| Voltar: destino | Retorno à entrada do sistema | Retorno à lista de ofícios; retorno original ausente, sem autorização | ausente |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Apoio de unidade | “Busque por sigla ou nome da unidade.” | Redação não exibida junto ao campo correspondente; sem autorização | ausente |
| Agrupamento dos assinantes | “Assinantes e destinatário”; “Demais assinantes” | Grupos não exibidos; sem autorização | ausente |

Valores preenchidos e vazios pertencem a configurações diferentes, não provam erro de inicialização. Pendente: catálogo de assinantes do destino, atributos completos de cada campo, consulta de CEP, cascatas, validação, mensagens após envio e permissões. P01 impede dispensar PT/OS ou encerrar a meta correspondente. Nada foi alterado para contornar essa decisão. Diárias documentadas separadamente.

## Consulta de CEP e decisão sobre o formulário

O destino passou a resolver `/viagens/cadastros/api/cep/<cep>/`, sem gravar endereço ou configuração. O contrato usa cep, logradouro, bairro, cidade, uf e estado, com respostas 400 para formato inválido, 404 para CEP inexistente e 502 para indisponibilidade. A leitura exige acesso ao módulo; o endpoint aceita GET. O nome do estado prioriza a base local, como o serviço da origem. O cliente HTTP utiliza urllib, já usado no projeto; nenhuma biblioteca foi acrescentada.

A consulta real do serviço do destino ao exemplo 01001000 retornou Praça da Sé, Sé, São Paulo/SP. [Documentação oficial do ViaCEP](https://viacep.com.br/), [resultado e validação](validacao-cep.json). Isso não prova o funcionamento da ida completa pelo formulário nem a resposta autenticada do GV. O navegador recusou abrir diretamente os endereços JSON com `net::ERR_BLOCKED_BY_CLIENT`; não foi criada captura substituta nem certificação visual.

P10 solicita autorização para o fluxo institucional: retirar da aba os campos que não pertencem a ela, preservando-os no banco, derivar UF/cidade-sede pelo endereço e adotar as validações de CEP/telefone. [Impacto nos campos](configuracao-impacto-formulario.json). O formulário atual permanece até a decisão. P01 sobre assinantes PT/OS continua independente e pendente.

Os testes verificam formato sem chamada externa, contrato de sucesso, ausência de criação de configuração, falha/timeout, CEP não encontrado, estado de fallback, acesso ao módulo e recusa de POST. 131 testes de cadastros passaram em cada banco. Nenhum dado institucional foi alterado nos ensaios.
