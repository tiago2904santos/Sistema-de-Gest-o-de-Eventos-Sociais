"""Diário da carga: ligações a registros nativos não mudam sua procedência."""

import uuid

from django.db import models


class Lote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    areas = models.JSONField()
    opcoes = models.JSONField(default=dict)
    criado_em = models.DateTimeField(auto_now_add=True)
    desfeito_em = models.DateTimeField(null=True)


class Etapa(models.Model):
    lote = models.ForeignKey(Lote, on_delete=models.PROTECT)
    nome = models.CharField(max_length=30)
    concluida_em = models.DateTimeField(auto_now=True)
    relatorio = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lote", "nome"], name="f6_etapa_lote_unica")]


class Registro(models.Model):
    lote = models.ForeignKey(Lote, on_delete=models.PROTECT)
    etapa = models.CharField(max_length=30)
    tabela = models.CharField(max_length=100)
    origem_pk = models.CharField(max_length=64)
    modelo = models.CharField(max_length=100)
    destino_pk = models.CharField(max_length=64)
    criado = models.BooleanField(default=True)
    # Somente campos efetivamente alterados em registros nativos. Senhas e
    # tokens não entram aqui: a senha nativa jamais é substituída.
    antes = models.JSONField(default=dict)
    depois = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64)
    arquivos = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tabela", "origem_pk"], name="f6_registro_origem_unica")]


class Vinculo(models.Model):
    """Somente os vínculos M2M criados pela carga, reversíveis individualmente."""

    lote = models.ForeignKey(Lote, on_delete=models.PROTECT)
    modelo = models.CharField(max_length=120)
    destino_pk = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["modelo", "destino_pk"], name="f6_vinculo_destino_unico")]
