"""A conversa, e o que ela deixa gravado.

Três tabelas, e cada uma existe por um motivo:

``Conversa`` e ``Mensagem`` são a trilha do que foi pedido e do que foi
respondido. Num sistema que produz documento oficial, "o assistente disse que
podia" precisa ser verificável depois — inclusive quando a pessoa jura que
pediu outra coisa.

``AcaoPendente`` é o que separa este assistente de um chatbot: enquanto ela
existe e não foi confirmada, **nada foi gravado**. Ela guarda o rascunho, qual
campo está sendo perguntado e o resumo que a pessoa leu antes de decidir. Uma
confirmação registra quem confirmou e quando; um cancelamento registra que
houve, e o rascunho fica.

O rascunho guarda **ids**, nunca o texto falado: é isso que garante que a
confirmação mostre a pessoa de verdade, e não a aproximação que o assistente
fez dela.
"""

from django.conf import settings
from django.db import models


class Conversa(models.Model):
    class Canal(models.TextChoices):
        PAINEL = "PAINEL", "Painel do sistema"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.CASCADE,
        related_name="conversas_assistente",
    )
    canal = models.CharField("canal", max_length=20, choices=Canal.choices, default=Canal.PAINEL)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["-atualizado_em"]
        verbose_name = "conversa do assistente"
        verbose_name_plural = "conversas do assistente"

    def __str__(self):
        return f"Conversa #{self.pk} — {self.usuario}"

    @property
    def pendente(self):
        """A ação em andamento, se houver — só pode haver uma por conversa."""
        return self.acoes.exclude(
            status__in=[AcaoPendente.Status.CONFIRMADA, AcaoPendente.Status.CANCELADA]
        ).first()


class Mensagem(models.Model):
    class Autor(models.TextChoices):
        PESSOA = "PESSOA", "Pessoa"
        ASSISTENTE = "ASSISTENTE", "Assistente"

    conversa = models.ForeignKey(
        Conversa, verbose_name="conversa", on_delete=models.CASCADE, related_name="mensagens"
    )
    autor = models.CharField("autor", max_length=20, choices=Autor.choices)
    texto = models.TextField("texto")
    # Qual ferramenta respondeu — a resposta deixa de ser opinião e passa a ter
    # procedência rastreável.
    ferramenta = models.CharField("ferramenta", max_length=60, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        ordering = ["criado_em", "pk"]
        verbose_name = "mensagem do assistente"
        verbose_name_plural = "mensagens do assistente"

    def __str__(self):
        return f"{self.get_autor_display()}: {self.texto[:60]}"


class AcaoPendente(models.Model):
    class Status(models.TextChoices):
        COLETANDO = "COLETANDO", "Coletando dados"
        AGUARDANDO = "AGUARDANDO", "Aguardando confirmação"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        CANCELADA = "CANCELADA", "Cancelada"

    conversa = models.ForeignKey(
        Conversa, verbose_name="conversa", on_delete=models.CASCADE, related_name="acoes"
    )
    ferramenta = models.CharField("ferramenta", max_length=60)
    rascunho = models.JSONField("rascunho", default=dict, blank=True)
    # O que o pedido original trouxe e ainda não foi resolvido. Quando uma
    # ambiguidade interrompe o preenchimento ("qual Silva?"), o resto do que a
    # pessoa disse — o motorista, a viatura — espera aqui em vez de se perder.
    extraidos = models.JSONField("extraídos do pedido", default=dict, blank=True)
    aguardando_campo = models.CharField("campo em pergunta", max_length=60, blank=True)
    status = models.CharField(
        "status", max_length=20, choices=Status.choices, default=Status.COLETANDO
    )
    resultado = models.JSONField("resultado", default=dict, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    resolvido_em = models.DateTimeField("resolvido em", null=True, blank=True)
    resolvido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="resolvido por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acoes_assistente_resolvidas",
    )

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "ação pendente do assistente"
        verbose_name_plural = "ações pendentes do assistente"

    def __str__(self):
        return f"{self.ferramenta} ({self.get_status_display()})"


# ── Canal WhatsApp ─────────────────────────────────────────────────────────
#
# O canal é deliberadamente burro: ele recebe texto, entrega ao orquestrador e
# devolve texto. Nenhuma regra de negócio mora aqui — é o que permitiu o
# WhatsApp ser a menor parte do trabalho, e é o que faria um segundo canal
# (Telegram, app próprio) custar quase nada.
#
# As duas caixas existem porque a Meta espera um 200 em segundos e reentrega o
# que não confirmou. Gravar primeiro e processar depois dá as duas coisas de
# graça: resposta rápida e idempotência por `wa_message_id`.


class VinculoWhatsApp(models.Model):
    """Autorização de um número a falar pelo sistema, em nome de alguém.

    Sem vínculo ativo, a mensagem é ignorada em silêncio — responder a um
    número desconhecido confirmaria que o sistema existe e ainda gastaria
    conversa paga.

    O vínculo é a trilha: quem autorizou, quando, e quando o número falou pela
    última vez. Esse último carimbo é o que decide se ainda dá para responder
    de graça (ver `JANELA_DE_SERVICO_HORAS`).
    """

    # A Meta entrega o remetente sem "+" e só com dígitos; é assim que ele é
    # guardado, para a comparação ser exata em vez de depender de formatação.
    numero = models.CharField("número (E.164, só dígitos)", max_length=20, unique=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.CASCADE,
        related_name="vinculos_whatsapp",
    )
    ativo = models.BooleanField("ativo", default=True)
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="autorizado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vinculos_whatsapp_autorizados",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    ultima_entrada_em = models.DateTimeField("última mensagem recebida", null=True, blank=True)

    class Meta:
        ordering = ["numero"]
        verbose_name = "vínculo de WhatsApp"
        verbose_name_plural = "vínculos de WhatsApp"

    def __str__(self):
        return f"{self.numero} → {self.usuario}"


class MensagemRecebida(models.Model):
    """O que chegou pelo webhook, gravado antes de qualquer processamento."""

    class Tipo(models.TextChoices):
        TEXTO = "TEXTO", "Texto"
        AUDIO = "AUDIO", "Áudio"
        OUTRO = "OUTRO", "Outro"

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        PROCESSADA = "PROCESSADA", "Processada"
        IGNORADA = "IGNORADA", "Ignorada"
        ERRO = "ERRO", "Erro"

    # A chave da idempotência: a Meta reentrega o que não recebeu 200, e sem
    # isto a mesma frase viraria duas viagens.
    wa_message_id = models.CharField("id da mensagem", max_length=120, unique=True)
    numero = models.CharField("número de origem", max_length=20, db_index=True)
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices, default=Tipo.TEXTO)
    texto = models.TextField("texto", blank=True)
    media_id = models.CharField("id da mídia", max_length=120, blank=True)
    status = models.CharField(
        "status", max_length=12, choices=Status.choices, default=Status.PENDENTE, db_index=True
    )
    erro = models.TextField("erro", blank=True)
    conversa = models.ForeignKey(
        Conversa,
        verbose_name="conversa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensagens_whatsapp",
    )
    recebida_em = models.DateTimeField("recebida em", auto_now_add=True)
    processada_em = models.DateTimeField("processada em", null=True, blank=True)

    class Meta:
        ordering = ["recebida_em", "pk"]
        verbose_name = "mensagem recebida do WhatsApp"
        verbose_name_plural = "mensagens recebidas do WhatsApp"

    def __str__(self):
        return f"{self.numero}: {(self.texto or self.tipo)[:50]}"


class MensagemEnviada(models.Model):
    """A resposta a caminho. Fila simples, sem broker, porque não precisa."""

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        ENVIADA = "ENVIADA", "Enviada"
        ERRO = "ERRO", "Erro"

    numero = models.CharField("número de destino", max_length=20, db_index=True)
    texto = models.TextField("texto")
    resposta_a = models.ForeignKey(
        MensagemRecebida,
        verbose_name="resposta a",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="respostas",
    )
    status = models.CharField(
        "status", max_length=10, choices=Status.choices, default=Status.PENDENTE, db_index=True
    )
    tentativas = models.PositiveIntegerField("tentativas", default=0)
    erro = models.TextField("erro", blank=True)
    wa_message_id = models.CharField("id da mensagem", max_length=120, blank=True)
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    enviada_em = models.DateTimeField("enviada em", null=True, blank=True)

    class Meta:
        ordering = ["criada_em", "pk"]
        verbose_name = "mensagem enviada pelo WhatsApp"
        verbose_name_plural = "mensagens enviadas pelo WhatsApp"

    def __str__(self):
        return f"{self.numero}: {self.texto[:50]}"
