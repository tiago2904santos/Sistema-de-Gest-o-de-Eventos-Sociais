"""Modelos do controle de publicações da ASCOM.

Espelham o "Relatório de Publicações": cada linha da planilha é uma pauta
que entra pela assessoria, passa por redação, edição e revisão e sai
publicada no site da PCPR (e, eventualmente, na AEN). Os cadastros de apoio
(equipe e unidades) existem para padronizar nomes e alimentar os filtros.
"""

import datetime as dt

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Responsavel(models.Model):
    """Integrante da equipe de comunicação (ou parceiro, como SESP e AEN)."""

    nome = models.CharField("nome", max_length=100, unique=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "responsável da equipe"
        verbose_name_plural = "responsáveis da equipe"

    def __str__(self):
        return self.nome


class Unidade(models.Model):
    """Unidade policial responsável pela pauta (DP, DHPP, DPC...)."""

    nome = models.CharField("nome", max_length=150, unique=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "unidade responsável"
        verbose_name_plural = "unidades responsáveis"

    def __str__(self):
        return self.nome


class StatusPublicacao(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
    PUBLICADA = "PUBLICADA", "Publicada"
    CANCELADA = "CANCELADA", "Cancelada"


CSS_STATUS_PUBLICACAO = {
    StatusPublicacao.PENDENTE: "pendente",
    StatusPublicacao.EM_ANDAMENTO: "em_andamento",
    StatusPublicacao.PUBLICADA: "publicada",
    StatusPublicacao.CANCELADA: "cancelada",
}


class Publicacao(models.Model):
    """Pauta jornalística, da entrada até a publicação."""

    data = models.DateField("data da pauta")
    jornalista = models.ForeignKey(
        Responsavel,
        verbose_name="jornalista responsável",
        on_delete=models.PROTECT,
        related_name="pautas",
    )
    unidade = models.ForeignKey(
        Unidade,
        verbose_name="unidade responsável",
        on_delete=models.PROTECT,
        related_name="pautas",
        blank=True,
        null=True,
    )
    fonte = models.CharField(
        "fonte da pauta", max_length=200, blank=True,
        help_text="Quem passou a informação (delegado, investigador, assessoria).",
    )
    inicio_pauta = models.TimeField("início da pauta", blank=True, null=True)
    titulo = models.CharField("título da pauta", max_length=300)
    status = models.CharField(
        "status",
        max_length=15,
        choices=StatusPublicacao.choices,
        default=StatusPublicacao.PENDENTE,
    )
    andamento = models.TextField("andamento", blank=True)
    colocada_edicao = models.TimeField("colocada para edição", blank=True, null=True)
    data_publicacao = models.DateField("data de publicação", blank=True, null=True)
    horario_publicacao = models.TimeField(
        "horário de publicação", blank=True, null=True
    )
    revisao = models.ForeignKey(
        Responsavel,
        verbose_name="revisão",
        on_delete=models.PROTECT,
        related_name="pautas_revisadas",
        blank=True,
        null=True,
    )
    galeria_fotos = models.ForeignKey(
        Responsavel,
        verbose_name="galeria de fotos",
        on_delete=models.PROTECT,
        related_name="pautas_galeria",
        blank=True,
        null=True,
    )
    bitly_grupos = models.BooleanField("Bitly nos grupos", blank=True, null=True)
    enviado_sesp = models.BooleanField("enviado para a SESP", blank=True, null=True)
    publicado_aen = models.BooleanField("publicado na AEN", blank=True, null=True)
    link_site = models.URLField("link no site da PCPR", max_length=500, blank=True)
    link_aen = models.URLField("link na AEN", max_length=500, blank=True)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criado por",
        on_delete=models.PROTECT,
        related_name="publicacoes_criadas",
        blank=True,
        null=True,
    )
    chave_importacao = models.CharField(
        "chave da importação", max_length=64, unique=True, blank=True, null=True
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["-data", "-inicio_pauta", "-pk"]
        verbose_name = "publicação"
        verbose_name_plural = "publicações"
        indexes = [
            models.Index(fields=["status", "data"], name="publicacao_status_data_idx"),
            models.Index(fields=["data_publicacao"], name="publicacao_data_pub_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(data_publicacao__isnull=True)
                    | models.Q(data_publicacao__gte=models.F("data"))
                ),
                name="publicacao_publicada_apos_pauta",
            ),
        ]

    def __str__(self):
        return self.titulo

    def clean(self):
        super().clean()
        erros = {}
        if self.data_publicacao and self.data and self.data_publicacao < self.data:
            erros["data_publicacao"] = (
                "A publicação não pode ser anterior à data da pauta."
            )
        if self.status == StatusPublicacao.PUBLICADA and not self.data_publicacao:
            erros["data_publicacao"] = "Informe a data em que a pauta foi publicada."
        if erros:
            raise ValidationError(erros)

    @property
    def status_css(self):
        return CSS_STATUS_PUBLICACAO.get(self.status, "pendente")

    @property
    def publicada(self):
        return self.status == StatusPublicacao.PUBLICADA

    @property
    def encerrada(self):
        return self.status in {StatusPublicacao.PUBLICADA, StatusPublicacao.CANCELADA}

    @property
    def tempo_ate_publicacao(self):
        """timedelta entre o início da pauta e a publicação (None se faltar dado)."""
        if not (self.data and self.inicio_pauta and self.data_publicacao and self.horario_publicacao):
            return None
        inicio = dt.datetime.combine(self.data, self.inicio_pauta)
        fim = dt.datetime.combine(self.data_publicacao, self.horario_publicacao)
        if fim < inicio:
            return None
        return fim - inicio

    @property
    def tempo_ate_publicacao_display(self):
        delta = self.tempo_ate_publicacao
        if delta is None:
            return ""
        return formatar_duracao(delta)


def formatar_duracao(delta):
    """"1h25" / "2d 3h" para a leitura humana dos tempos de publicação."""
    total = int(delta.total_seconds() // 60)
    dias, resto = divmod(total, 24 * 60)
    horas, minutos = divmod(resto, 60)
    if dias:
        return f"{dias}d {horas}h"
    return f"{horas}h{minutos:02d}"
