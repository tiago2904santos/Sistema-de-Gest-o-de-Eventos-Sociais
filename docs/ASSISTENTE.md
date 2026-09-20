# Assistente

Um assistente operacional que consulta e prepara viagens **conversando**, pelo
painel do sistema e — quando o canal existir — pelo WhatsApp.

Ele não é um chat sobre o sistema: é uma porta para o sistema. O que ele faz,
faz pelos mesmos `services`/`selectors` das telas, com as permissões de quem
está conversando e com confirmação humana antes de qualquer gravação.

Para conferir com as próprias mãos, o roteiro de testes práticos está em
[`TESTES_PRATICOS.md`](TESTES_PRATICOS.md).

## O que já funciona

| Você diz | Ele faz |
| --- | --- |
| "quem vai para Maringá em setembro?" | Lista servidores, motorista e datas |
| "quais viagens desta semana?" | Lista as viagens do período |
| "o que está pendente?" | Diários sem KM, prestações não iniciadas, ofícios em rascunho, viagens sem termo |
| "faça os documentos para um evento em Maringá dia 18, vai o João Silva com o motorista Pereira" | Pergunta o que faltou, mostra o resumo e, após confirmação, cria viagem + roteiro + ofício + termo em rascunho |

## Custo

**Zero, por padrão.** O interpretador de fábrica é determinístico: ele casa o
que foi dito contra o próprio cadastro, sem chamar API nenhuma. Nenhuma
variável de ambiente é necessária, e nenhum dado sai da rede.

Configurar `ANTHROPIC_API_KEY` troca só o interpretador — o assistente passa a
entender frases mais soltas. O que ele **pode fazer** não muda: mesmas
ferramentas, mesmas permissões, mesma confirmação. Ver `.env.example`.

## Desenho

```
mensagem
   ↓
orquestrador ──── há ação aguardando confirmação? → só "confirmar"/"cancelar"
   │         ──── há campo em pergunta?           → a mensagem é a resposta
   ↓
interpretador (determinístico | API)   → escolhe UMA ferramenta + parâmetros
   ↓
resolução contra o cadastro            → ambíguo vira pergunta, nunca palpite
   ↓
ferramenta: permissão do usuário       → grava? então resumo + confirmação
   ↓
services.py dos módulos existentes
```

Quatro garantias, e cada uma tem teste:

1. **A permissão é a de quem conversa.** O assistente não tem grupo nem acesso
   próprio (`assistente/permissions.py`).
2. **Nada é gravado sem confirmação.** Enquanto a `AcaoPendente` não for
   confirmada, o banco não mudou.
3. **Na dúvida, pergunta.** Dois servidores "Silva" viram menu, não escolha.
4. **Nome que o cadastro não conhece é dito em voz alta**, nunca descartado em
   silêncio.

## Arquivos

| Arquivo | Papel |
| --- | --- |
| `ferramentas.py` | Contrato: parâmetros tipados, permissão, `mutante` |
| `catalogo.py` | As ferramentas concretas |
| `resolucao.py` | Texto → registro do banco, com ambiguidade |
| `periodos.py` | "setembro", "dia 18", "essa semana" → datas |
| `formulario.py` | Quais campos faltam e qual perguntar |
| `orquestrador.py` | O laço da conversa |
| `llm/` | Interpretadores plugáveis |

## Canal WhatsApp

Só de entrada: **você escreve, ele responde**. Não há mensagem proativa, o
que mantém tudo dentro da janela de serviço de 24h — que é gratuita — e
dispensa templates aprovados.

```
Meta ──POST──▶ /whatsapp/webhook/
                 │ confere a assinatura HMAC
                 │ grava e responde 200  (sem processar)
                 ▼
            MensagemRecebida (PENDENTE)
                 │
      manage.py processar_whatsapp
                 │ número → vínculo → usuário
                 │ áudio → transcrição local
                 ▼
            orquestrador  ← o MESMO do painel
                 ▼
            MensagemEnviada → Cloud API
```

### Por que gravar antes de processar

A Meta espera 200 em segundos e reentrega o que não confirmou. Transcrever um
áudio dentro do request estouraria o prazo, a Meta reentregaria, e a mesma
fala viraria duas viagens. Gravar primeiro dá resposta rápida e idempotência
(por `wa_message_id`) de uma vez só.

### Decisões que não são óbvias

- **Sem segredo configurado, o webhook recusa tudo.** Falha fechado: a
  variável esquecida no `.env` do servidor é exatamente como um webhook chega
  aberto em produção.
- **Número sem vínculo é ignorado em silêncio.** Responder confirmaria que o
  sistema existe e ainda abriria conversa paga.
- **O nono dígito.** O `wa_id` brasileiro vem com e sem o 9 conforme a idade
  do cadastro; `numeros.variantes()` tenta as duas formas. Sem isso o vínculo
  não casa e o assistente parece quebrado só para algumas pessoas.
- **A permissão continua sendo a do usuário vinculado.** O canal não afrouxa
  nada — quem só consulta pelas telas também só consulta pelo WhatsApp.

### Operação

```bash
manage.py processar_whatsapp             # uma passada
manage.py processar_whatsapp --loop      # sob supervisor
```

Tarefa agendada de minuto em minuto serve: repetir é seguro, porque a
idempotência está no banco.

O vínculo número ↔ usuário é cadastrado no admin (`Vínculos de WhatsApp`), com
registro de quem autorizou. Não é autoatendimento, de propósito.

### Custo

Entrada e resposta dentro da janela: **gratuito**. Transcrição:
`pip install faster-whisper`, roda na CPU do próprio servidor — o áudio não
sai da rede, e nem o texto precisa sair, já que o interpretador padrão também
é local.

## Próximos passos

- **Ferramentas de outros módulos**: quando entrar a primeira fora de Viagens,
  o assistente ganha código de módulo próprio e o recorte passa a ser por
  ferramenta (ver o comentário em `apps.py`).
- **Segundo canal** (Telegram, app próprio): o orquestrador não muda; só a
  tradução de formato, como em `assistente/whatsapp/payload.py`.
