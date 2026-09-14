# Viatura — confirmação direta de exclusão

Meta 0 aberta; Meta 1 parcial após P04. [Origem](imagens/meta1-viatura-exclusao-direta-origem.png), [destino](imagens/meta1-viatura-exclusao-direta-destino.png), [observação](imagens/meta1-viatura-exclusao-direta-observacao.json). Comparadas a viatura AAA1234 da origem e a viatura temporária ZZZ0Z97 do destino. As tabelas descrevem somente o estado preventivo efetivamente observado.

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Dados editáveis | Nenhum; identificação pela placa | Nenhum; identificação pela placa | igual |
| Placa em destaque | AAA1234 | ZZZ0Z97, outro registro de ensaio | adaptado — bases distintas; mesma apresentação do valor sem máscara adicional |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Contexto | Página própria ao abrir a URL de exclusão | Página própria ao abrir a URL de exclusão | igual |
| Composição visual | Painel de confirmação no tema GV | Painel e controles DS V3.2 | adaptado — mudança de pele autorizada na seção 2 |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Voltar | Retorna à lista sem excluir; exercitado | Retorna à lista sem excluir; exercitado | igual |
| Confirmação disponível | Botão “Excluir viatura” | Botão “Excluir viatura” | igual |
| Abrir pelo teclado | Botão Excluir acionado por Space abre a confirmação e foca Voltar | Mesmo comportamento observado | igual |
| Circular o foco | Shift+Tab de Voltar leva a Excluir; Tab de Excluir leva a Voltar | Mesmo ciclo observado, corrigido para não perder foco fora do diálogo | igual |
| Cancelar pelo teclado | Escape fecha a confirmação sem envio | Mesmo fechamento observado sem envio | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Títulos da página e painel | “Excluir viatura?” em ambos | Mesmos títulos | igual |
| Permanência | “Esta ação é permanente e não poderá ser desfeita.” | Mesma mensagem | igual |
| Identificação | “Você está prestes a excluir” seguido da placa | Mesmo texto com a placa do ensaio | igual |
| Vínculos | “Se houver vínculos com outros registros, a exclusão será bloqueada.” | Mesma mensagem | igual |

O GET não excluiu registros e Voltar preservou as viaturas nos dois sistemas. [Cancelamento](imagens/meta1-viatura-exclusao-cancelamento-ensaio.json). Depois, somente a viatura temporária do destino foi excluída: retorno à lista e “Viatura excluída com sucesso.” [Resposta](imagens/meta1-viatura-excluida-resposta-ensaio.json). Nenhuma exclusão foi confirmada na origem.

Pendente: POST com sucesso e bloqueio na origem, comparação de vínculos equivalentes, perfis sem permissão e falhas de requisição. Os testes do destino verificam confirmação GET, retorno à lista mesmo com next e bloqueio de vínculo criado durante a exclusão sem auditoria de sucesso. Isso não certifica estados não exercitados na origem.

## Teclado das confirmações após P04 — 10/09/2026

Comparação real: o destino antes deixava o foco sair do diálogo ao usar Shift+Tab em Voltar; o GV o levava ao botão Excluir. O ciclo foi alinhado. A ação da lista agora usa botão, como a origem, permitindo abertura por Space. O envio continua no botão Excluir dentro da confirmação, com a mesma URL, permissões e regras da view.

Pares: [meta1-viaturas-exclusao-teclado](imagens/meta1-viaturas-exclusao-teclado-observacao.json), [meta1-viaturas-exclusao-ciclo-foco](imagens/meta1-viaturas-exclusao-ciclo-foco-observacao.json). [Sequência de teclas e foco](imagens/meta1-dialogos-teclado-ensaio.json); [validação](validacao-dialogos.json). Capturas JPEG originais, sem edição, na galeria.

Somente no destino, três registros temporários foram criados e removidos para exercitar as listas vazias: combustível 4, unidade 99 e viatura 3 (ZZT9T91). Nenhum servidor foi vinculado. Ausência desses registros confirmada no banco. Os demais registros foram apenas usados para abrir e cancelar diálogos. Nenhum POST na origem. Sucesso e bloqueios após POST da origem continuam pendentes; a comparação do teclado não os certifica.
