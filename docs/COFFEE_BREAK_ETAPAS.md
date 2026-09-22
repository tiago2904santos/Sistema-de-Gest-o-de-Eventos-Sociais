# Coffee Break — as três etapas da solicitação

A solicitação de coffee break segue o caminho do processo de pagamento
26.617.058-0 (NF 8957, Favo e Mel), em três telas com o stepper da prestação
de contas:

| Etapa | Tela | O que sai dela |
|---|---|---|
| 1. Solicitação e OS | `solicitacoes/<pk>/editar/` | Ordem de serviço (PDF) |
| 2. Nota fiscal, ofício e certifico | `solicitacoes/<pk>/nota/` | Ofício ao GAF e certifico digital (PDF) |
| 3. Protocolo e pagamento | `solicitacoes/<pk>/protocolo/` | Textos do eProtocolo (com Copiar) e o anexo completo (PDF único ou ZIP) |

Cada etapa grava só os seus campos (`PedidoCoffeeBreakForm`,
`NotaCoffeeBreakForm`, `ProtocoloCoffeeBreakForm`); salvar uma etapa não
apaga o que foi preenchido nas outras.

## Documentos

Os três documentos são HTML convertido em PDF pelo WeasyPrint, medidos nos
modelos em uso (posições em pontos, fontes e entrelinhas dos originais):

- `templates/coffee_break/documentos/ordem_servico.html` — a OS 41/2026;
- `templates/coffee_break/documentos/certifico.html` — o certifico do processo;
- `templates/coffee_break/documentos/oficio.html` — o Of. 124/2026.

O brasão e a marca PCPR (`static/img/*-timbre.png`) foram tirados do PDF da OS.

## Anexo do protocolo

Na ordem do processo: ofício, nota fiscal, certifico, certidões (FGTS,
trabalhista, municipal, estadual, federal), termo aditivo (se o contrato
tiver) e contrato. A etapa 3 mostra o que falta em cada linha; o PDF único e o
ZIP (um arquivo por documento, numerado) só saem com tudo pronto e as
certidões vigentes.

## O que se configura

- **Cadastros › Ofício e eProtocolo** (registro único): vocativo, quem assina o
  ofício e o cargo, o bloco do destinatário, o assunto e as palavras-chave do
  eProtocolo e o destino do despacho. Os valores iniciais são os do processo.
- **Cadastros › Fornecedores › nome curto**: o nome que vai no detalhamento do
  eProtocolo, ex. `ENVIO P/ PAGAMENTO DA NOTA FISCAL N 8957 - (FAVO E MEL)`.
  Em branco, usa a razão social sem o "LTDA".
- **Cadastros › Contratos › cláusula do pagamento**: citada no ofício
  (padrão: "Cláusula Décima, item 10.2.6").
