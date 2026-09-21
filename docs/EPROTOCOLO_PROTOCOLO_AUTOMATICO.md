# Protocolo automático do ofício (eProtocolo/PR)

Antes, o número do protocolo era aberto no eProtocolo em outra aba e digitado
no campo **Protocolo** do ofício. Agora o caminho se inverte: ao salvar o
ofício, o sistema abre o processo no eProtocolo e traz o número de volta para
o campo.

## O que acontece na tela

| Situação | Comportamento |
|---|---|
| Campo vazio, ao salvar (rascunho ou finalizar) | O sistema abre o protocolo e preenche o campo. A tela mostra "Protocolo 12.345.678-9 aberto no eProtocolo." |
| Campo vazio, com credencial **de treinamento** | O processo é aberto de verdade no barramento de teste, e o aviso diz: "aberto no eProtocolo de treinamento — é um processo de teste e NÃO vale como protocolo oficial." |
| Campo preenchido à mão | Nada é aberto. O número informado é preservado e a ficha o marca como **manual**. |
| Sem credenciais configuradas | O número é **simulado**, no formato certo, com aviso amarelo na tela e marca `SIMULADO` no banco. |
| eProtocolo fora do ar, credencial vencida, código institucional faltando | **O ofício é salvo assim mesmo.** A falha vira aviso; a conferência continua cobrando "Informe o protocolo." antes de finalizar. |
| Ofício ainda sem número/motivo | Em rascunho não diz nada (é cedo); ao finalizar, avisa o que falta. |

O protocolo **não** é aberto na criação do rascunho — só na gravação. O
"Novo ofício" reaproveita rascunhos vazios abandonados, e abrir processo ali
dentro seria abrir processo para ofício que nunca existiu.

## Treinamento não é produção

Só `EPROTOCOLO_AMBIENTE=producao` gera protocolo **oficial**. Em
`treinamento` e `homologacao` a chamada sai de verdade e o processo existe no
barramento de teste — mas ninguém pode protocolar com aquele número. O
sistema trata os três casos como três coisas distintas, e nunca deixa a
diferença implícita:

| `protocolo_origem` | Significado |
|---|---|
| `EPROTOCOLO` | Aberto em produção — vale como protocolo oficial |
| `TREINAMENTO` | Aberto no barramento de teste (treinamento/homologação) — **não** vale |
| `SIMULADO` | Gerado aqui, sem sair para a rede (sem credencial) — **não** vale |
| `MANUAL` | Digitado por uma pessoa |

Em todos os casos não oficiais o aviso aparece três vezes: na mensagem depois
de salvar, na ajuda abaixo do campo Protocolo e na saída do
`eprotocolo_check`. O número fica gravado no campo (é o que permite ensaiar o
fluxo inteiro), e quem protocolar de fato digita o número real por cima — o
que devolve a origem para `MANUAL`.

## Como sair do modo simulado

São três condições, todas no `.env` do servidor:

1. `EPROTOCOLO_AMBIENTE=treinamento` (ou `homologacao`/`producao`);
2. `EPROTOCOLO_BASE_URL`, `TOKEN_URL`, `CLIENT_ID`, `CLIENT_SECRET` e
   `CONSUMER_ID` preenchidos — credenciais do barramento `spi-servicos`,
   pedidas à Celepar/SEAP;
3. `EPROTOCOLO_REAL_READONLY=False` — a trava que libera gravação. Com ela
   fechada (padrão), o sistema só consulta e a abertura é recusada com
   mensagem explícita, em vez de abrir processo por engano.

Além disso, o eProtocolo exige códigos institucionais na abertura:
`EPROTOCOLO_COD_ORGAO_PADRAO`, `COD_LOCAL_ORIGEM_PADRAO`,
`COD_ASSUNTO_VIAGEM` e `COD_ESPECIE_OFICIO`. Faltando qualquer um, nada sai
para a rede — o aviso na tela nomeia a variável que falta.

Para desligar tudo e voltar ao preenchimento manual:
`EPROTOCOLO_AUTO_PROTOCOLO_OFICIO=0`.

## Diagnóstico

```bash
python manage.py eprotocolo_check            # configuração, sem tocar a rede
python manage.py eprotocolo_check --escopos  # escopos OAuth2 a solicitar
python manage.py eprotocolo_ping             # autentica e faz uma leitura
```

Nenhum dos dois grava coisa alguma no eProtocolo. As credenciais saem
mascaradas; o `client_secret` nunca é exibido.

## Onde mora o código

```
integracoes/eprotocolo/     # a conversa com o barramento
  settings.py               # ambiente, credenciais, travas
  client.py                 # transporte (urllib), token, mascaramento
  services.py               # uma função por operação
  mappers.py                # ofício → payload
  mocks.py                  # respostas do modo simulado
viagens_oficios/
  protocolo_services.py     # a regra do ofício: quando abrir, o que gravar
```

O pacote foi portado do Gerenciador de Viagens (app `protocolos` +
`integracoes.eprotocolo`), com o transporte reescrito em `urllib`: este
projeto não tem `requests` no `requirements.txt`.

## O que ficou de fora

- **Enviar o PDF do ofício para dentro do protocolo**, tramitar e acompanhar
  situação. O barramento tem esses endpoints e o client já sabe falar com
  eles; falta a regra de negócio e a tela.
- **Conferir os paths da API** (`/v3/protocolos`, …) contra a documentação
  oficial antes do go-live em produção. Em modo simulado eles não são usados.
- **Ofício criado pelo assistente** nasce sem número e sem protocolo; ele
  chega quando a pessoa abre e salva o ofício no sistema, como o próprio
  assistente já orienta.
