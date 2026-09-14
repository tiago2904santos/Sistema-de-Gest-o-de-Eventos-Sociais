"""Identidade de origem, sem dependência de um app de domínio."""

from django.db import models


class OrigemLegado(models.Model):
    """As classes concretas declaram a unicidade condicional do par."""

    legado_origem = models.CharField("origem no legado", max_length=50, blank=True)
    legado_pk = models.PositiveIntegerField("id no legado", blank=True, null=True)

    class Meta:
        abstract = True


class OrigemLegadoUUID(OrigemLegado):
    # Os dois modelos documentais do GV usam UUID, não um inteiro.
    legado_pk = models.UUIDField("id no legado", blank=True, null=True)

    class Meta:
        abstract = True
