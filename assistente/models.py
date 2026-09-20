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
