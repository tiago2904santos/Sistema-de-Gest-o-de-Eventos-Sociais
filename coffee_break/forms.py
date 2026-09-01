"""Formulários do módulo de Coffee Break.

Como nos demais módulos, a renderização fica com os components do design
system; aqui mora a validação e a persistência.
"""

from django import forms
from django.db.models import Q, Sum

from .models import (
    ContratoCoffeeBreak,
    Fornecedor,
    LoteCoffeeBreak,
    SituacaoFinanceira,
    SolicitacaoCoffeeBreak,
    normalizar_cnpj,
)
from . import services


def _queryset_lotes(instance_pk_lote=None):
    """Lotes ativos + o lote já vinculado (histórico continua legível)."""
    qs = LoteCoffeeBreak.objects.filter(ativo=True)
    if instance_pk_lote:
        qs = qs | LoteCoffeeBreak.objects.filter(pk=instance_pk_lote)
    return qs.select_related("contrato__fornecedor").distinct()


class SolicitacaoCoffeeBreakForm(forms.ModelForm):
    versao = forms.CharField(required=False, widget=forms.HiddenInput)

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
        if instancia:
            self.initial["versao"] = str(
                int(instancia.atualizado_em.timestamp() * 1_000_000)
            )
            if instancia.financeiro_iniciado:
                for nome in (
                    "lote",
                    "data_solicitacao",
                    "numero",
                    "descricao_evento",
                    "quantidade",
                    "data_inicio_evento",
                    "data_fim_evento",
                    "periodo_evento_texto",
                ):
                    self.fields[nome].disabled = True

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
        texto = (dados.get("periodo_evento_texto") or "").strip()
        campos_periodo = {
            "data_inicio_evento", "data_fim_evento", "periodo_evento_texto"
        }
        if texto and (inicio or fim) and (
            not self.instance.pk or campos_periodo.intersection(self.changed_data)
        ):
            self.add_error(
                "periodo_evento_texto",
                "Use as datas estruturadas ou o período em texto, não os dois.",
            )
        if self.instance.pk:
            atual = type(self.instance).objects.filter(pk=self.instance.pk).values_list(
                "atualizado_em", flat=True
            ).first()
            versao = dados.get("versao")
            if atual and versao != str(int(atual.timestamp() * 1_000_000)):
                raise forms.ValidationError(
                    "Esta solicitação foi alterada por outra pessoa. Recarregue a página antes de salvar."
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


class FormularioCadastroVersionado(forms.ModelForm):
    """Evita que duas correções administrativas se sobrescrevam."""

    versao = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["versao"] = str(
                int(self.instance.atualizado_em.timestamp() * 1_000_000)
            )

    def clean(self):
        dados = super().clean()
        if self.instance.pk:
            atual = type(self.instance).objects.filter(pk=self.instance.pk).values_list(
                "atualizado_em", flat=True
            ).first()
            if atual and dados.get("versao") != str(
                int(atual.timestamp() * 1_000_000)
            ):
                raise forms.ValidationError(
                    "Este cadastro foi alterado por outra pessoa. Recarregue a página antes de salvar."
                )
        return dados


class FornecedorForm(FormularioCadastroVersionado):
    cnpj = forms.CharField(
        label="CNPJ",
        required=False,
        max_length=18,
        help_text="Pode ser informado com ou sem pontuação.",
    )

    class Meta:
        model = Fornecedor
        fields = ("razao_social", "cnpj", "contato", "telefone", "email", "ativo")

    def clean_cnpj(self):
        cnpj = normalizar_cnpj(self.cleaned_data.get("cnpj"))
        if cnpj and len(cnpj) != 14:
            raise forms.ValidationError("O CNPJ deve ter 14 dígitos.")
        return cnpj


class ContratoCoffeeBreakForm(FormularioCadastroVersionado):
    class Meta:
        model = ContratoCoffeeBreak
        fields = (
            "fornecedor",
            "numero",
            "numero_gms",
            "termo_aditivo",
            "fiscal_responsavel",
            "objeto",
            "observacoes",
            "ativo",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        fornecedor_atual = self.instance.fornecedor_id if self.instance.pk else None
        self.fields["fornecedor"].queryset = Fornecedor.objects.filter(
            Q(ativo=True) | Q(pk=fornecedor_atual)
        ).distinct()


class LoteCoffeeBreakForm(FormularioCadastroVersionado):
    class Meta:
        model = LoteCoffeeBreak
        fields = (
            "contrato",
            "numero",
            "exercicio",
            "quantidade_total",
            "empenho",
            "municipios",
            "municipios_texto",
            "orientacoes",
            "especificacoes_tecnicas",
            "observacoes",
            "ativo",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        contrato_atual = self.instance.contrato_id if self.instance.pk else None
        self.fields["contrato"].queryset = ContratoCoffeeBreak.objects.filter(
            Q(ativo=True) | Q(pk=contrato_atual)
        ).select_related("fornecedor").distinct()
        self.fields["municipios"].queryset = self.fields["municipios"].queryset.select_related(
            "estado"
        ).order_by("nome", "estado__sigla")

    def clean_quantidade_total(self):
        quantidade = self.cleaned_data["quantidade_total"]
        if self.instance.pk:
            consumido = self.instance.solicitacoes.filter(cancelada=False).aggregate(
                total=Sum("quantidade")
            )["total"] or 0
            if quantidade < consumido:
                raise forms.ValidationError(
                    f"O lote já consumiu {consumido} unidades; a capacidade não pode ficar abaixo disso."
                )
        return quantidade
