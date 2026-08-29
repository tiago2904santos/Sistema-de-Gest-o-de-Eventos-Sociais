from django.conf import settings
from django.db import models


class LogAuditoria(models.Model):
    """Registro simples de ações relevantes no sistema."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs_auditoria",
    )
    acao = models.CharField("ação", max_length=100)
    descricao = models.TextField("descrição", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "log de auditoria"
        verbose_name_plural = "logs de auditoria"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.acao} — {self.criado_em:%d/%m/%Y %H:%M}"
