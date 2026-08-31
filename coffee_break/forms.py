"""Formulários do módulo de Coffee Break.

Como nos demais módulos, a renderização fica com os components do design
system; aqui mora a validação e a persistência.
"""

from django import forms

from .models import (
    Fornecedor,
    LoteCoffeeBreak,
    SituacaoFinanceira,
    SolicitacaoCoffeeBreak,
)
from . import services


def _queryset_lotes(instance_pk_lote=None):
    """Lotes ativos + o lote já vinculado (histórico continua legível)."""
    qs = LoteCoffeeBreak.objects.filter(ativo=True)
    if instance_pk_lote:
        qs = qs | LoteCoffeeBreak.objects.filter(pk=instance_pk_lote)
    return qs.select_related("contrato__fornecedor").distinct()


class SolicitacaoCoffeeBreakForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoCoffeeBreak
        fields = [
            "lote",
            "data_solicitacao",
            "numero",
            "descricao_evento",
            "quantidade",
            "data_inicio_evento",
            "data_fim_evento",
            "periodo_evento_texto",
            "numero_nota_fiscal",
            "protocolo_pagamento",
            "data_atesto_gaf",
            "data_ordem_bancaria",
            "data_envio_empresa",
            "observacoes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instancia = self.instance if self.instance.pk else None
        self.fields["lote"].queryset = _queryset_lotes(
            instancia and instancia.lote_id
        )
        self.fields["descricao_evento"].required = True
        self.fields["quantidade"].required = True

    def clean_quantidade(self):
        quantidade = self.cleaned_data.get("quantidade")
        if quantidade is not None and quantidade < 1:
            raise forms.ValidationError(
                "A quantidade deve ser de pelo menos 1 unidade."
            )
        return quantidade

    def clean(self):
        dados = super().clean()
        inicio = dados.get("data_inicio_evento")
        fim = dados.get("data_fim_evento")
        if inicio and fim and fim < inicio:
            self.add_error(
                "data_fim_evento",
                "A data de fim não pode ser anterior à data de início.",
            )
        # Identificadores institucionais são texto — nunca números coláveis
        # de datas: só normaliza espaços.
        for campo in ("numero", "numero_nota_fiscal", "protocolo_pagamento"):
            if dados.get(campo):
                dados[campo] = dados[campo].strip()
        return dados

    def save(self, criado_por=None):
        solicitacao = super().save(commit=False)
        if not solicitacao.pk:
            solicitacao.criado_por = criado_por
        # Trava o lote e revalida o saldo na mesma transação da escrita.
        return services.salvar_com_saldo(solicitacao)


class FiltroSolicitacoesCoffeeForm(forms.Form):
    """Filtros da listagem de solicitações (GET)."""

    q = forms.CharField(required=False, label="Busca")
    lote = forms.ModelChoiceField(
        required=False,
        label="Lote",
        queryset=LoteCoffeeBreak.objects.select_related(
            "contrato__fornecedor"
        ).all(),
    )
    fornecedor = forms.ModelChoiceField(
        required=False, label="Fornecedor", queryset=Fornecedor.objects.all()
    )
    situacao = forms.ChoiceField(
        required=False,
        label="Situação financeira",
        choices=[("", "Todas as situações")] + list(SituacaoFinanceira.choices),
    )
    inicio = forms.DateField(required=False, label="Eventos a partir de")
    fim = forms.DateField(required=False, label="Eventos até")


class FiltroLotesForm(forms.Form):
    """Filtros da listagem de lotes (GET)."""

    q = forms.CharField(required=False, label="Busca")
    exercicio = forms.CharField(required=False, label="Exercício")
    situacao = forms.ChoiceField(
        required=False,
        label="Situação",
        choices=[("", "Todas"), ("ativos", "Ativos"), ("inativos", "Inativos")],
    )
