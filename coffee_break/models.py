"""Modelos do controle de Coffee Break da ASCOM.

Espelham a planilha "CONTROLE COFFE ASCOM": fornecedores contratados,
contratos, lotes (com quantitativo por exercício) e as solicitações que
consomem o saldo de cada lote. Consumido e restante são sempre calculados
a partir das solicitações — nunca armazenados.
"""

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Coalesce
from django.utils import timezone


def normalizar_cnpj(valor):
    """Só os dígitos do CNPJ; devolve string vazia para valores vazios."""
    return re.sub(r"\D", "", valor or "")


def formatar_cnpj(digitos):
    if len(digitos) != 14:
        return digitos
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


class Fornecedor(models.Model):
    """Empresa contratada para fornecer o coffee break."""

    razao_social = models.CharField("razão social", max_length=200, unique=True)
    cnpj = models.CharField(
        "CNPJ",
        max_length=14,
        blank=True,
        help_text="Somente números; normalizado automaticamente.",
    )
    contato = models.CharField("contato", max_length=150, blank=True)
    telefone = models.CharField("telefone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "fornecedor de coffee break"
        verbose_name_plural = "fornecedores de coffee break"
        ordering = ["razao_social"]
        constraints = [
            # CNPJ não se repete entre fornecedores (vazio é permitido).
            models.UniqueConstraint(
                fields=["cnpj"],
                condition=~models.Q(cnpj=""),
                name="cnpj_unico_fornecedor",
            ),
        ]

    def __str__(self):
        return self.razao_social

    @property
    def cnpj_formatado(self):
        return formatar_cnpj(self.cnpj)

    def clean(self):
        super().clean()
        self.cnpj = normalizar_cnpj(self.cnpj)
        if self.cnpj and len(self.cnpj) != 14:
            raise ValidationError({"cnpj": "O CNPJ deve ter 14 dígitos."})

    def save(self, *args, **kwargs):
        self.cnpj = normalizar_cnpj(self.cnpj)
        super().save(*args, **kwargs)


class ContratoCoffeeBreak(models.Model):
    """Contrato administrativo que sustenta um ou mais lotes."""

    fornecedor = models.ForeignKey(
        Fornecedor,
        verbose_name="fornecedor",
        on_delete=models.PROTECT,
        related_name="contratos",
    )
    numero = models.CharField("número do contrato", max_length=30, unique=True)
    numero_gms = models.CharField("número GMS", max_length=30, blank=True)
    termo_aditivo = models.CharField("termo aditivo", max_length=50, blank=True)
    fiscal_responsavel = models.CharField(
        "fiscal responsável", max_length=150, blank=True,
        help_text="Fiscal que atesta as notas fiscais.",
    )
    objeto = models.CharField("objeto", max_length=255, blank=True)
    observacoes = models.TextField("observações", blank=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "contrato de coffee break"
        verbose_name_plural = "contratos de coffee break"
        ordering = ["numero"]

    def __str__(self):
        return f"Contrato {self.numero} — {self.fornecedor}"


class LoteQuerySet(models.QuerySet):
    def com_consumo(self):
        """Anota consumido e restante calculados das solicitações ativas."""
        consumido = Coalesce(
            models.Sum(
                "solicitacoes__quantidade",
                filter=models.Q(solicitacoes__cancelada=False),
            ),
            0,
        )
        return self.annotate(
            consumido=consumido,
            restante=models.F("quantidade_total") - consumido,
        )


class LoteCoffeeBreak(models.Model):
    """Lote contratado: quantitativo por exercício e municípios atendidos."""

    contrato = models.ForeignKey(
        ContratoCoffeeBreak,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="lotes",
    )
    numero = models.PositiveSmallIntegerField("número do lote")
    exercicio = models.CharField(
        "exercício", max_length=9,
        help_text="Vigência do quantitativo (ex.: 2026).",
    )
    quantidade_total = models.PositiveIntegerField(
        "quantidade total contratada", validators=[MinValueValidator(1)]
    )
    empenho = models.CharField("empenho", max_length=30, blank=True)
    municipios = models.ManyToManyField(
        "cadastros.Municipio",
        verbose_name="municípios abrangidos",
        related_name="lotes_coffee_break",
        blank=True,
    )
    municipios_texto = models.TextField(
        "municípios (texto original)", blank=True,
        help_text="Lista original da planilha, preservada integralmente.",
    )
    orientacoes = models.TextField("orientações", blank=True)
    especificacoes_tecnicas = models.TextField("especificações técnicas", blank=True)
    observacoes = models.TextField("observações", blank=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    objects = LoteQuerySet.as_manager()

    class Meta:
        verbose_name = "lote de coffee break"
        verbose_name_plural = "lotes de coffee break"
        ordering = ["-exercicio", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["contrato", "numero", "exercicio"],
                name="lote_unico_por_contrato_e_exercicio",
            ),
        ]

    def __str__(self):
        return f"Lote {self.numero} ({self.exercicio}) — {self.contrato.fornecedor}"

    @property
    def rotulo_curto(self):
        return f"Lote {self.numero} ({self.exercicio})"

    @property
    def quantidade_consumida(self):
        return (
            self.solicitacoes.filter(cancelada=False).aggregate(
                total=models.Sum("quantidade")
            )["total"]
            or 0
        )

    @property
    def saldo_restante(self):
        return self.quantidade_total - self.quantidade_consumida

    @property
    def percentual_consumido(self):
        if not self.quantidade_total:
            return 0
        return round(self.quantidade_consumida * 100 / self.quantidade_total)


class SituacaoFinanceira(models.TextChoices):
    """Situação derivada dos marcos preenchidos — nunca gravada no banco."""

    AGUARDANDO_NOTA_FISCAL = "AGUARDANDO_NOTA_FISCAL", "Aguardando nota fiscal"
    AGUARDANDO_PROTOCOLO = "AGUARDANDO_PROTOCOLO", "Aguardando protocolo"
    AGUARDANDO_ATESTO = "AGUARDANDO_ATESTO", "Aguardando atesto"
    AGUARDANDO_ORDEM_BANCARIA = (
        "AGUARDANDO_ORDEM_BANCARIA",
        "Aguardando ordem bancária",
    )
    AGUARDANDO_ENVIO_EMPRESA = (
        "AGUARDANDO_ENVIO_EMPRESA",
        "Aguardando envio à empresa",
    )
    CONCLUIDA = "CONCLUIDA", "Concluída"
    CANCELADA = "CANCELADA", "Cancelada"


class SolicitacaoCoffeeBreak(models.Model):
    """Pedido de coffee break contra o saldo de um lote."""

    lote = models.ForeignKey(
        LoteCoffeeBreak,
        verbose_name="lote",
        on_delete=models.PROTECT,
        related_name="solicitacoes",
    )
    data_solicitacao = models.DateField(
        "data da solicitação", default=timezone.localdate
    )
    data_inicio_evento = models.DateField(
        "data de início do evento", blank=True, null=True
    )
    data_fim_evento = models.DateField("data de fim do evento", blank=True, null=True)
    periodo_evento_texto = models.CharField(
        "período do evento (texto original)", max_length=120, blank=True,
        help_text="Períodos irregulares da planilha (ex.: \"23, 24 e 25/03\").",
    )
    numero = models.CharField(
        "número da solicitação", max_length=20, blank=True,
        help_text="Identificador institucional — sempre texto (ex.: 02/2026).",
    )
    descricao_evento = models.TextField("descrição do evento")
    quantidade = models.PositiveIntegerField("quantidade solicitada")
    numero_nota_fiscal = models.CharField(
        "número da nota fiscal", max_length=30, blank=True
    )
    protocolo_pagamento = models.CharField(
        "protocolo de pagamento", max_length=30, blank=True
    )
    data_atesto_gaf = models.DateField(
        "data de atesto e envio ao GAF", blank=True, null=True
    )
    data_ordem_bancaria = models.DateField(
        "ordem bancária emitida em", blank=True, null=True
    )
    data_envio_empresa = models.DateField(
        "ordem bancária enviada à empresa em", blank=True, null=True
    )
    observacoes = models.TextField("observações", blank=True)

    # Cancelamento auditável: o registro permanece, fora do consumo do lote.
    cancelada = models.BooleanField("cancelada", default=False)
    cancelada_em = models.DateTimeField("cancelada em", blank=True, null=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="cancelada por",
        on_delete=models.PROTECT,
        related_name="solicitacoes_coffee_canceladas",
        blank=True,
        null=True,
    )
    motivo_cancelamento = models.CharField(
        "motivo do cancelamento", max_length=255, blank=True
    )

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criado por",
        on_delete=models.PROTECT,
        related_name="solicitacoes_coffee_criadas",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "solicitação de coffee break"
        verbose_name_plural = "solicitações de coffee break"
        ordering = ["-data_solicitacao", "-criado_em"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(data_inicio_evento__isnull=True)
                    | models.Q(data_fim_evento__isnull=True)
                    | models.Q(data_fim_evento__gte=models.F("data_inicio_evento"))
                ),
                name="coffee_periodo_evento_valido",
            ),
            # Quantidade zero só sobrevive em registro cancelado (histórico).
            models.CheckConstraint(
                condition=models.Q(quantidade__gte=1) | models.Q(cancelada=True),
                name="coffee_quantidade_positiva",
            ),
        ]

    def __str__(self):
        rotulo = self.numero or f"#{self.pk}"
        return f"Coffee break {rotulo} — {self.lote.rotulo_curto}"

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.data_inicio_evento
            and self.data_fim_evento
            and self.data_fim_evento < self.data_inicio_evento
        ):
            errors["data_fim_evento"] = (
                "A data de fim não pode ser anterior à data de início."
            )
        if not self.cancelada and (self.quantidade or 0) < 1:
            errors["quantidade"] = "A quantidade deve ser de pelo menos 1 unidade."
        if errors:
            raise ValidationError(errors)

    @property
    def situacao_financeira(self):
        from . import services

        return services.situacao_financeira(self)

    @property
    def situacao_financeira_display(self):
        return SituacaoFinanceira(self.situacao_financeira).label

    @property
    def situacao_financeira_css(self):
        """Reusa as cores existentes dos status-badges do design system."""
        from . import services

        return services.CSS_SITUACAO[self.situacao_financeira]

    @property
    def periodo_evento_display(self):
        """Período legível: texto original quando irregular, datas quando não."""
        if self.periodo_evento_texto:
            return self.periodo_evento_texto
        if self.data_inicio_evento and self.data_fim_evento and (
            self.data_fim_evento != self.data_inicio_evento
        ):
            return (
                f"{self.data_inicio_evento:%d/%m/%Y} a "
                f"{self.data_fim_evento:%d/%m/%Y}"
            )
        if self.data_inicio_evento:
            return f"{self.data_inicio_evento:%d/%m/%Y}"
        return ""
