# Testes práticos do Assistente

Roteiro para conferir com as próprias mãos o que o assistente e o canal
WhatsApp fazem. Os comandos foram executados; onde há um "esperado", é o que
saiu de verdade.

A ordem importa: os primeiros testes não precisam de nada além do repositório,
e só o último precisa de conta na Meta.

> **Por que tantos testes de recusa.** Boa parte do roteiro confere o que o
> sistema **não** faz: não grava sem confirmação, não escolhe entre dois
> homônimos, não aceita POST sem assinatura, não responde a número
> desconhecido. Num sistema que gera documento oficial, essas são as garantias
> que importam — e são justamente as que passam despercebidas quando só se
> testa o caminho feliz.

## Preparação

```bash
git pull origin main

python -m venv .venv
.venv\Scripts\activate          # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
```

Superusuário atravessa todas as permissões — é o caminho curto. Para testar a
**restrição** de acesso você vai precisar de um usuário comum (teste 7).

Antes dos testes de tela, cadastre em **Viagens → Cadastros**:

- dois servidores **com o mesmo sobrenome** (é o que torna o teste 2 útil);
- um terceiro servidor, vinculado como motorista de alguma viatura;
- confira que há municípios (`manage.py importar_municipios` ou o seed).

---

## 1. A suíte automatizada

O teste mais rápido, e o de maior cobertura.

```bash
python manage.py test assistente
```

Esperado: `Ran 89 tests ... OK`.

Os nomes dizem o que cada um prova:

```bash
python manage.py test assistente --verbosity 2
```

Alguns que valem ler: `test_sobrenome_repetido_nao_escolhe_sozinho`,
`test_nada_e_gravado_antes_da_confirmacao`,
`test_o_resto_do_pedido_sobrevive_a_pergunta`,
`test_numero_guardado_com_nove_casa_com_a_entrega_sem_nove`.

---

## 2. O painel

```bash
python manage.py runserver
```

Abra `http://127.0.0.1:8000/assistente/`.

| Digite | Esperado |
| --- | --- |
| `o que está pendente?` | Diários sem KM, prestações, ofícios em rascunho |
| `quais viagens desta semana?` | A lista do período |
| `quem vai para Maringá em setembro?` | Nomes com as datas, motorista marcado |
| `quem vai para Xanxerê?` | "Não encontrei o município" — não inventa |
| `bom dia` | Oferece ajuda com exemplos |

### O teste que mais importa

```
faça os documentos para um evento em Maringá dia 18/11/2026, vai o Silva
```

Ele deve **perguntar qual Silva**, mostrando cargo e unidade para dar como
escolher. Responda `1`, depois o município sede, depois o motivo.

Aí vem o resumo — **leia com atenção, é o ponto do desenho inteiro.** Ele
mostra os valores já resolvidos: nome completo do servidor, município com UF,
data por extenso. É aqui que se percebe que "Pereira" virou "Ferreira".

Faça duas vezes:

1. responda `cancelar` → confira em Viagens que **nada foi criado**;
2. repita e responda `confirmar` → viagem, roteiro, ofício em rascunho e termo
   aparecem.

O ofício nasce **sem número**: a numeração é recurso escasso e só é reservada
quando alguém finaliza o documento pela tela.

---

## 3. O WhatsApp, sem a Meta

Simula a Meta inteira, localmente. É o teste mais completo do canal.

```bash
set WHATSAPP_APP_SECRET=segredo-local
set WHATSAPP_VERIFY_TOKEN=verify-local
python manage.py runserver 127.0.0.1:8765
```

*(Linux/Mac: `export` em vez de `set`.)*

### 3a. Handshake de cadastro

```bash
curl "http://127.0.0.1:8765/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=verify-local&hub.challenge=DESAFIO123"
```

Esperado: `DESAFIO123` em texto puro. Com token errado: **403**.

### 3b. Vincular um número

No admin: `/admin/assistente/vinculowhatsapp/add/`. Só dígitos, sem `+`:
`5541999998888`. O vínculo guarda quem autorizou — é decisão administrativa,
não autoatendimento.

### 3c. Uma mensagem assinada

```bash
SEGREDO=segredo-local
CORPO='{"object":"whatsapp_business_account","entry":[{"id":"1","changes":[{"field":"messages","value":{"messaging_product":"whatsapp","metadata":{"phone_number_id":"123"},"messages":[{"from":"554199998888","id":"wamid.teste.1","timestamp":"1790000000","type":"text","text":{"body":"o que está pendente?"}}]}}]}]}'
ASSINATURA="sha256=$(printf '%s' "$CORPO" | openssl dgst -sha256 -hmac "$SEGREDO" | sed 's/^.*= //')"

curl -X POST http://127.0.0.1:8765/whatsapp/webhook/ \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $ASSINATURA" \
  -d "$CORPO"
```

Esperado: `{"recebidas": 1}`.

Repare no remetente: `554199998888`, **sem** o nono dígito, contra um vínculo
guardado **com** ele. Tem que casar. É o erro que faria o assistente "não
responder pra algumas pessoas" — e só para elas.

### 3d. Processar

```bash
python manage.py processar_whatsapp
```

Esperado: `1 processada(s), 0 enviada(s)`. Zero enviadas porque não há token
real da Meta — a resposta fica na fila. Em
`/admin/assistente/mensagemenviada/` você lê o texto que sairia, com o motivo
da recusa vindo da própria Meta.

### 3e. A conversa inteira pelo canal

Repita o 3c trocando o texto e o `id` (**precisa ser único**), rodando
`processar_whatsapp` entre cada passo:

1. `faça os documentos para um evento em Maringá dia 18/11/2026, vai o Silva com o motorista Pereira`
2. `1`
3. `Curitiba`
4. `Operação PCPR Mais Perto`
5. `confirmar`

É a mesma conversa do painel. Não há regra duplicada no canal: a permissão, a
desambiguação e a confirmação vêm do mesmo orquestrador.

---

## 4. Segurança do webhook

| Teste | Esperado |
| --- | --- |
| POST sem cabeçalho de assinatura | **403** |
| POST com `X-Hub-Signature-256: sha256=0000` | **403** |
| Assinar um corpo e enviar outro | **403** |
| Tirar `WHATSAPP_APP_SECRET` e reiniciar | **403** em tudo |

O último é o mais importante. **Sem segredo configurado, o webhook recusa
tudo** — falha fechado. Se aceitasse, bastaria a variável não ter sido copiada
para o `.env` do servidor e a URL viraria um endereço público que aceita
qualquer comando em nome de um número vinculado.

---

## 5. Idempotência

Mande o **mesmo** `wamid.teste.1` duas vezes.

Esperado: a segunda responde `{"recebidas": 0}` e nada duplica.

Vale repetir com a mensagem de `confirmar` do teste 3e e conferir que existe
**uma** viagem, não duas. A Meta reentrega o que não confirma em segundos; sem
essa garantia, a mesma frase viraria duas viagens.

---

## 6. Número desconhecido

Mande com `"from":"5511000000000"`, sem vínculo cadastrado.

Esperado: `{"recebidas": 1}`, mas no admin a mensagem fica **IGNORADA** e
**nenhuma resposta** é gerada. Responder confirmaria que o sistema existe e
ainda abriria conversa paga.

---

## 7. Permissão

Crie um usuário comum, coloque-o num setor com o módulo `VIAGENS`, mas **sem**
os grupos `VIAGENS_GESTOR` e `VIAGENS_OPERADOR`. Entre com ele e peça:

```
faça os documentos para um evento em Maringá dia 18/11/2026, vai o João Silva
```

Esperado: *"Isso está fora do seu acesso — eu uso exatamente as suas
permissões."* Consultar continua funcionando.

O assistente não tem grupo nem acesso próprio: ele empresta o de quem está
conversando. A pergunta "o que o assistente pode fazer?" tem uma resposta só —
o que aquela pessoa já podia.

---

## 8. Áudio (opcional)

```bash
pip install faster-whisper
```

Na primeira execução o modelo é baixado (~500 MB) e fica em cache. Roda na CPU;
o áudio não sai da rede.

**Sem instalar**, mande um payload de áudio (troque o bloco `text` por
`"type":"audio","audio":{"id":"m.1"}`) e confira que ele responde *"a
transcrição não está instalada neste servidor, me manda por texto"* — em vez de
o áudio sumir em silêncio.

---

## 9. Com a Meta de verdade

Só aqui é preciso conta. A Meta oferece um **número de teste gratuito** que
envia para até 5 destinatários verificados — suficiente para validar com o
próprio celular.

1. App em `developers.facebook.com` → adicione o produto WhatsApp.
2. Copie **App Secret**, **token de acesso** e **Phone Number ID** para o `.env`
   (nomes em `.env.example`).
3. O webhook precisa de **HTTPS público**. Para testar: `ngrok http 8000` e use
   a URL do ngrok + `/whatsapp/webhook/`.
4. Cadastre a URL e o `WHATSAPP_VERIFY_TOKEN` no painel da Meta e assine o
   campo `messages`.
5. `python manage.py processar_whatsapp --loop`
6. Mande mensagem do seu celular para o número de teste.

Em produção, o `--loop` fica sob um supervisor, ou uma tarefa agendada chama o
comando sem argumento de minuto em minuto. Repetir é seguro: a idempotência
está no banco.

---

## O que observar em qualquer teste

- **Nada é gravado antes da confirmação.** Enquanto a `AcaoPendente` está
  aberta, o banco não mudou.
- **Na dúvida, ele pergunta.** Homônimo vira menu, nunca palpite.
- **Nome que o cadastro não conhece é dito em voz alta**, nunca descartado em
  silêncio — senão você leria um resumo sem aquele servidor e poderia
  confirmar assim mesmo.
- **A procedência aparece.** No painel, cada resposta traz "via
  `<ferramenta>`"; no banco, a `Conversa` guarda a íntegra.
