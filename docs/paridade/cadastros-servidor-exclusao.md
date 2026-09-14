# Servidor — confirmação e bloqueio de exclusão

**Meta 0 aberta; estados diferentes observados, sem certificação.** [Origem](imagens/meta0-servidor-exclusao-origem.png), [destino](imagens/meta0-servidor-exclusao-destino.png). Na origem foi aberto e fechado o diálogo de ADEMAR SCHONS; no destino foi aberta a confirmação de APJ- ROBSON PAES. **Nenhuma exclusão foi confirmada.** Registros diferentes impedem concluir equivalência do bloqueio por vínculos.

**Correção após P04:** [diálogo atual da origem](imagens/meta1-servidores-confirmacao-origem.png)/[diálogo atual do destino](imagens/meta1-servidores-confirmacao-destino.png). Ambos foram abertos e fechados por Voltar, sem confirmar exclusão. As tabelas passam a comparar a confirmação preventiva atual; o bloqueio por vínculos continua na mesma view protegida do destino e permanece coberto pelos testes existentes.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Edição de dados | Nenhum campo de edição no diálogo | Nenhum campo de edição no diálogo | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Contexto da confirmação | Diálogo sobre a lista de servidores | Diálogo sobre a lista de servidores | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Voltar sem excluir | Botão Voltar fecha o diálogo; exercitado | Botão Voltar fecha o diálogo; exercitado | igual |
| Abrir pelo teclado | Botão Excluir acionado por Space abre a confirmação e foca Voltar | Mesmo comportamento observado | igual |
| Circular o foco | Shift+Tab de Voltar leva a Excluir; Tab de Excluir leva a Voltar | Mesmo ciclo observado, corrigido para não perder foco fora do diálogo | igual |
| Cancelar pelo teclado | Escape fecha a confirmação sem envio | Mesmo fechamento observado sem envio | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Título da superfície aberta | “Excluir servidor?” | “Excluir servidor?” | igual |
| Aviso de vínculos e permanência | “Se houver vínculos com outros registros, a exclusão será bloqueada.”; “Esta ação é permanente e não poderá ser desfeita.” | Mesmas mensagens na confirmação preventiva | igual |

A captura inicial da Meta 0 registrava uma página própria de bloqueio no destino, com identificação da solicitação de evento. Esse é um estado histórico, substituído pela resposta de exclusão na própria lista; os vínculos e impedimentos de exclusão continuam preservados.

Após P04, abrir diretamente a URL de exclusão por GET retornou à lista nos dois sistemas, sem excluir. No destino, o servidor temporário 7, “ENSAIO RESPOSTAS SERVIDOR 20260910”, foi criado como rascunho, atualizado para completo e excluído pelo diálogo da lista. A mensagem observada foi “Servidor excluído com sucesso.”; o registro temporário foi removido. [Ensaio de resposta](imagens/meta1-servidor-excluido-resposta-ensaio.json).

Os testes verificam preservação de vínculos com eventos, retorno seguro, ausência de remoção por GET e auditoria somente após sucesso. A origem possui uma proteção adicional no serviço para histórico de prestação de contas com comprovantes, assinatura ou solicitação numerada, com mensagem detalhada. Essa regra não foi alterada no destino nem certificada por comparação de POST. Pendente: equivalência dos bloqueios específicos, mensagens após POST na origem e perfis sem permissão; a origem permaneceu somente leitura.


## Retorno da exclusão

Corrigido o link da lista que alimenta a ação do diálogo: agora inclui o next validado, como observado no GV. O par `meta1-servidores-exclusao-retorno` registra as duas confirmações sem enviar. O destino foi exercitado com o servidor temporário 8 (ENSAIO RETORNO P11 20260910): criação e remoção pelo navegador, mensagem de sucesso, lista com retorno preservado e ausência do registro confirmada no banco. A origem não recebeu POST.

O teste de resposta passou a extrair o href real da lista e enviar POST a ele, sem inserir next artificialmente no corpo; verifica retorno e auditoria. Cinco testes de respostas em cada banco passaram. [Validação](validacao-servidores-retorno.json). P11 autoriza o botão e o retorno na busca/criação do destino; não dispensa bloqueios específicos de exclusão ou outras diferenças.

## Teclado das confirmações após P04 — 10/09/2026

Comparação real: o destino antes deixava o foco sair do diálogo ao usar Shift+Tab em Voltar; o GV o levava ao botão Excluir. O ciclo foi alinhado. A ação da lista agora usa botão, como a origem, permitindo abertura por Space. O envio continua no botão Excluir dentro da confirmação, com a mesma URL, permissões e regras da view.

Pares: [meta1-servidores-exclusao-espaco](imagens/meta1-servidores-exclusao-espaco-observacao.json), [meta1-servidores-exclusao-tab-inverso](imagens/meta1-servidores-exclusao-tab-inverso-observacao.json), [meta1-servidores-exclusao-tab-direto](imagens/meta1-servidores-exclusao-tab-direto-observacao.json), [meta1-servidores-exclusao-escape](imagens/meta1-servidores-exclusao-escape-observacao.json), [meta1-servidores-exclusao-botao-retorno](imagens/meta1-servidores-exclusao-botao-retorno-observacao.json). [Sequência de teclas e foco](imagens/meta1-dialogos-teclado-ensaio.json); [validação](validacao-dialogos.json). Capturas JPEG originais, sem edição, na galeria.

Somente no destino, três registros temporários foram criados e removidos para exercitar as listas vazias: combustível 4, unidade 99 e viatura 3 (ZZT9T91). Nenhum servidor foi vinculado. Ausência desses registros confirmada no banco. Os demais registros foram apenas usados para abrir e cancelar diálogos. Nenhum POST na origem. Sucesso e bloqueios após POST da origem continuam pendentes; a comparação do teclado não os certifica.
