# Assistente

Um assistente operacional que consulta e prepara viagens **conversando**, pelo
painel do sistema e — quando o canal existir — pelo WhatsApp.

Ele não é um chat sobre o sistema: é uma porta para o sistema. O que ele faz,
faz pelos mesmos `services`/`selectors` das telas, com as permissões de quem
está conversando e com confirmação humana antes de qualquer gravação.

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

## Próximos passos

- **WhatsApp**: só entrada (webhook + vínculo número ↔ usuário) e transcrição
  de áudio com Whisper local. O orquestrador já é agnóstico de canal —
  `Conversa.Canal.WHATSAPP` existe para isso.
- **Ferramentas de outros módulos**: quando entrar a primeira fora de Viagens,
  o assistente ganha código de módulo próprio e o recorte passa a ser por
  ferramenta (ver o comentário em `apps.py`).
