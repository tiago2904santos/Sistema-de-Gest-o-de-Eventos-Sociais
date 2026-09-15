# Meta 3 — Ofícios · Formulário (wizard)

**Origem:** `oficios:dados_viajantes`, `transporte`, `wizard_roteiro`, `wizard_justificativa`, `wizard_resumo` e `wizard_documentos` — seis páginas com gravação automática (`*_autosave`).
**Destino:** `viagens_oficios:novo` e `editar`, em `pages/viagens_oficios/form.html`, `form_context.py` e `static/js/viagens-oficios.js`; etapas 5 e 6 em [oficios-detalhe.md](oficios-detalhe.md).
**Data:** 14/09/2026.

## Como esta comparação foi feita

A origem **não tem fotografia deste formulário** neste repositório: a Meta 0 registrou a lista e os menus, e o Gerenciador de Viagens não estava disponível no ambiente desta rodada. A régua usada foi o conjunto de campos do modelo portado na Fase 4 (`Oficio`, `Justificativa`), as regras de conferência de cada etapa já portadas em `services.py` (`avaliar_oficio_dados_viajantes`, `avaliar_oficio_transporte`, `pendencias_motorista_documento`, `_pendencias_roteiro_documento`, `justificativas_services`) e a descrição das etapas no documento de metas ("identidade, motivo, equipe, transporte, cartão de motorista externo, roteiro com resumo da rota, conferência e resumo"). **A conferência lado a lado com a tela da origem continua devida** e está listada nas decisões (P18).

Capturas do destino: [edição](imagens/meta3-oficio-form-destino.png) ([antes](imagens/meta3-oficio-form-antes.png)), [motorista externo e viatura não cadastrada](imagens/meta3-oficio-form-motorista-externo-destino.png), [novo](imagens/meta3-oficio-form-novo-destino.png).

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Data do ofício | `data_criacao`, obrigatória, calendário | igual, calendário do sistema | igual |
| Protocolo | `protocolo`, nove dígitos com ou sem pontuação | igual, com ajuda "Nove dígitos, com ou sem pontuação." | igual |
| Assunto | `assunto`, texto livre | igual, com a nota de que não vai para o documento | igual |
| Unidade solicitante | `solicitante`, escolha | igual, busca por sigla ou nome | igual |
| Modelo de motivo e Motivo | escolher o modelo preenche o texto; padrão sugerido no novo | igual | igual |
| Custeio e observação | três opções; observação obrigatória para "Outra instituição" | igual; a obrigatoriedade é validada no servidor e marcada na tela | igual |
| Viajantes | escolha múltipla de servidores com cargo e unidade | lista de servidores com "Viaja" e busca por nome, cargo ou unidade | **adaptado**: sem fotografia do controle da origem |
| Servidores com termo de autorização | subconjunto dos viajantes | caixa "Termo" por viajante, habilitada só para quem viaja; o servidor descarta quem não viaja | igual |
| Viatura | cadastrada, ou placa/modelo/combustível/tipo manuais | "Cadastrada / Não cadastrada": só o bloco escolhido aparece; escolher a cadastrada apaga a manual | igual |
| Identificação do motorista | Servidor ou Manual | igual | igual |
| Motorista (servidor) | escolha; fora da equipe exige ofício e protocolo de origem | igual; o aviso e os dois campos aparecem quando o escolhido não está entre os viajantes | igual |
| Cartão do motorista externo | nome, RG, CPF, cargo, unidade, observação | igual, com máscaras de RG e CPF do módulo de cadastros | igual |
| Ofício e protocolo do motorista | `motorista_oficio_referencia` (número/ano) e `motorista_protocolo_ref` | iguais, com a ajuda "Referência no formato número/ano (ex.: 15/2026)." | igual |
| Porte/transporte de armas | marcado por padrão | chave marcada por padrão | igual |
| Roteiro | escolha do roteiro com resumo da rota; "Montar roteiro" leva ao editor | escolha com busca por sede ou destino; "Resumo da rota" com sede, percurso, destinos, período, trechos, servidores, quantidade e valor das diárias por extenso; "Montar roteiro" e "Abrir roteiro" em nova aba | igual |
| Regra de prazo | primeira saída, data do ofício, antecedência, prazo mínimo e avaliação | iguais, com o selo Obrigatória / Não exigida / Regra pendente | igual |
| Modelo e texto da justificativa | escolher o modelo preenche o texto; texto obrigatório quando a regra exige | igual | igual |
| Quantidade de servidores nas diárias | snapshot gravado ao salvar a equipe | igual (`diarias_quantidade_servidores`) | igual |

## Listagem (etapas)

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Seis etapas em seis páginas, com navegação entre elas | wizard | uma tela com seis seções numeradas e a lateral de etapas (1–4 rolam até a seção; 5 é a conferência na própria tela; 6 abre a tela de documentos) | **adaptado**: decisão 7 da Fase 4 (wizard vira formulário longo com lateral), registrada no plano mestre |
| Estado de cada etapa | concluída / pendente, pelas regras de conferência | igual: Concluído / Pendente / Não exigida, pelas mesmas funções | igual |
| Gravação automática | `*_autosave` a cada etapa | não há; a tela grava ao salvar | **ausente** — aguarda decisão (P19) |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Avançar de etapa | botão de cada página do wizard | "Salvar e conferir" grava tudo e abre a conferência (etapa 5) | **adaptado** |
| Voltar | volta à lista ou à etapa anterior | "Voltar" para onde a tela foi aberta (`?next=`) ou para a conferência | igual |
| Novo ofício | POST cria o rascunho numerado e abre a etapa 1 | igual (`viagens_oficios:criar`) | igual |
| Erro de validação | por etapa | resumo no topo com atalho para cada campo, e o erro junto ao campo | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Ofício cancelado | não observado | aviso no topo com o motivo; a edição continua permitida | **adaptado** |
| Pendências da conferência | "Informe o protocolo.", "Selecione ao menos um viajante.", "Complete o transporte (viatura ou placa manual e motorista).", "Associe um roteiro ao ofício.", "Informe a justificativa obrigatória para este ofício." etc. | as mesmas frases (vêm de `services.py`, portado da origem) | igual |
| Pronto | — | "Ofício N pronto para emissão. Os documentos são gerados na etapa 6, na tela de conferência." | **adaptado** |

## O que mudou no destino nesta meta

- `_campos.html` deixou de renderizar o formulário do ofício: cada bloco está escrito em `form.html`. O laço genérico continua existindo apenas para as telas de configuração institucional, numeração e assinantes (Meta 1, P10) e para o cadastro de termo (Meta 5); sai quando essas telas forem tratadas.
- `form_context.py` monta o contexto bloco a bloco e o estado das seis etapas; `viagens-oficios.js` faz as regras de habilitação (viatura, motorista, referência de origem, custeio, termo por viajante, resumo da rota).
- `OficioForm.clean` apaga a viatura manual quando há cadastrada e exige a observação para custeio de outra instituição.
