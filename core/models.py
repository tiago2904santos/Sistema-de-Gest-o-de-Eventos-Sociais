from django.conf import settings
from django.db import models
from django.utils import timezone


class ModeloTemporal(models.Model):
    """Base abstrata com carimbos de criação e atualização."""

    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class ModeloCancelavel(models.Model):
    """Base abstrata para entidades canceláveis com motivo e reativação."""

    cancelado = models.BooleanField("cancelado", default=False)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)
    cancelado_em = models.DateTimeField("cancelado em", blank=True, null=True)

    class Meta:
        abstract = True

    def cancelar(self, motivo=""):
        self.cancelado = True
        self.motivo_cancelamento = motivo
        self.cancelado_em = timezone.now()
        self.save(update_fields=["cancelado", "motivo_cancelamento", "cancelado_em"])

    def reativar(self):
        self.cancelado = False
        self.motivo_cancelamento = ""
        self.cancelado_em = None
        self.save(update_fields=["cancelado", "motivo_cancelamento", "cancelado_em"])


class Notificacao(models.Model):
    """Notificação interna exibida no sino do cabeçalho."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.CASCADE,
        related_name="notificacoes",
    )
    # Sem o vínculo, apagar uma solicitação deixava a notificação apontando
    # para uma página inexistente; o cascade remove as duas juntas.
    solicitacao = models.ForeignKey(
        "solicitacoes.SolicitacaoEvento",
        verbose_name="solicitação",
        on_delete=models.CASCADE,
        related_name="notificacoes",
        blank=True,
        null=True,
    )
    titulo = models.CharField("título", max_length=150)
    mensagem = models.CharField("mensagem", max_length=255, blank=True)
    link = models.CharField("link", max_length=255, blank=True)
    lida = models.BooleanField("lida", default=False)
    criada_em = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "notificação"
        verbose_name_plural = "notificações"
        ordering = ["-criada_em"]
        indexes = [
            models.Index(fields=["usuario", "lida"]),
        ]

    def __str__(self):
        return f"{self.usuario} — {self.titulo}"
