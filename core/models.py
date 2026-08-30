from django.conf import settings
from django.db import models


class Notificacao(models.Model):
    """Notificação interna exibida no sino do cabeçalho."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.CASCADE,
        related_name="notificacoes",
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
