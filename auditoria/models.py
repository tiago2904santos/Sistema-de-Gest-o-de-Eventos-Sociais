from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    """Trilha imutável de criações, atualizações e exclusões.

    Gravada automaticamente por signals (``auditoria/signals.py``) nos apps
    auditados, com o delta dos campos alterados. Uma linha escrita nunca é
    atualizada nem apagada — ``save`` de update e ``delete`` levantam erro.
    """

    class Acao(models.TextChoices):
        CRIACAO = "CRIACAO", "Criação"
        ATUALIZACAO = "ATUALIZACAO", "Atualização"
        EXCLUSAO = "EXCLUSAO", "Exclusão"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_auditoria",
    )
    acao = models.CharField("ação", max_length=12, choices=Acao.choices)
    modelo = models.CharField("modelo", max_length=120, db_index=True)
    objeto_id = models.CharField("id do objeto", max_length=120, db_index=True)
    objeto_repr = models.CharField("representação", max_length=255, blank=True)
    alteracoes = models.JSONField("alterações", default=dict, blank=True)
    caminho_requisicao = models.CharField(
        "caminho da requisição", max_length=500, blank=True
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(
                fields=["modelo", "objeto_id", "-criado_em"],
                name="auditoria_objeto_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_acao_display()} de {self.modelo}#{self.objeto_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise TypeError("RegistroAuditoria é imutável; não há atualização.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("RegistroAuditoria é imutável; não há exclusão.")


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
