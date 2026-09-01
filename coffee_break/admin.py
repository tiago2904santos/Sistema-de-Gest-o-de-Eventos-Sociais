from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Sum

from .models import (
    ContratoCoffeeBreak,
    Fornecedor,
    LoteCoffeeBreak,
    HistoricoCoffeeBreak,
    SolicitacaoCoffeeBreak,
)


class HistoricoCoffeeBreakInline(admin.TabularInline):
    model = HistoricoCoffeeBreak
    extra = 0
    can_delete = False
    readonly_fields = ("usuario", "acao", "descricao", "criado_em")


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ("razao_social", "cnpj_formatado", "contato", "telefone", "ativo")
    list_filter = ("ativo",)
    search_fields = ("razao_social", "cnpj", "contato", "email")

    @admin.display(description="CNPJ")
    def cnpj_formatado(self, obj):
        return obj.cnpj_formatado or "—"


class LoteInline(admin.TabularInline):
    model = LoteCoffeeBreak
    extra = 0
    fields = ("numero", "exercicio", "quantidade_total", "empenho", "ativo")
    show_change_link = True


@admin.register(ContratoCoffeeBreak)
class ContratoCoffeeBreakAdmin(admin.ModelAdmin):
    list_display = ("numero", "fornecedor", "numero_gms", "fiscal_responsavel", "ativo")
    list_filter = ("ativo", "fornecedor")
    search_fields = ("numero", "numero_gms", "fornecedor__razao_social")
    inlines = [LoteInline]


class LoteCoffeeBreakAdminForm(forms.ModelForm):
    class Meta:
        model = LoteCoffeeBreak
        fields = "__all__"

    def clean_quantidade_total(self):
        """Impede reduzir a capacidade abaixo do que já foi consumido."""
        quantidade = self.cleaned_data["quantidade_total"]
        if self.instance.pk:
            consumido = (
                self.instance.solicitacoes.filter(cancelada=False).aggregate(
                    total=Sum("quantidade")
                )["total"]
                or 0
            )
            if quantidade < consumido:
                raise ValidationError(
                    f"O lote já consumiu {consumido} unidades; a capacidade "
                    "não pode ficar abaixo disso."
                )
        return quantidade


@admin.register(LoteCoffeeBreak)
class LoteCoffeeBreakAdmin(admin.ModelAdmin):
    form = LoteCoffeeBreakAdminForm
    list_display = (
        "numero",
        "exercicio",
        "contrato",
        "quantidade_total",
        "consumido",
        "restante",
        "ativo",
    )
    list_filter = ("ativo", "exercicio", "contrato__fornecedor")
    search_fields = (
        "contrato__numero",
        "contrato__fornecedor__razao_social",
        "municipios_texto",
    )
    filter_horizontal = ("municipios",)
    readonly_fields = ("consumido", "restante", "criado_em", "atualizado_em")

    @admin.display(description="Consumido")
    def consumido(self, obj):
        return obj.quantidade_consumida if obj.pk else "—"

    @admin.display(description="Restante")
    def restante(self, obj):
        return obj.saldo_restante if obj.pk else "—"


class SolicitacaoCoffeeBreakAdminForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoCoffeeBreak
        fields = "__all__"

    def clean(self):
        dados = super().clean()
        lote = dados.get("lote")
        quantidade = dados.get("quantidade")
        cancelada = dados.get("cancelada")
        if lote and quantidade and not cancelada:
            consumo = lote.solicitacoes.filter(cancelada=False)
            if self.instance.pk:
                consumo = consumo.exclude(pk=self.instance.pk)
            consumido = consumo.aggregate(total=Sum("quantidade"))["total"] or 0
            restante = lote.quantidade_total - consumido
            if quantidade > restante:
                self.add_error(
                    "quantidade",
                    f"Quantidade acima do saldo do lote: restam {restante} "
                    f"de {lote.quantidade_total} unidades.",
                )
        return dados


@admin.register(SolicitacaoCoffeeBreak)
class SolicitacaoCoffeeBreakAdmin(admin.ModelAdmin):
    form = SolicitacaoCoffeeBreakAdminForm
    list_display = (
        "numero",
        "lote",
        "descricao_resumida",
        "data_solicitacao",
        "quantidade",
        "situacao",
        "cancelada",
    )
    list_filter = ("cancelada", "lote__exercicio", "lote")
    search_fields = (
        "numero",
        "descricao_evento",
        "numero_nota_fiscal",
        "protocolo_pagamento",
    )
    date_hierarchy = "data_solicitacao"
    readonly_fields = (
        "situacao",
        "cancelada_em",
        "cancelada_por",
        "criado_em",
        "atualizado_em",
    )
    inlines = (HistoricoCoffeeBreakInline,)

    @admin.display(description="Evento")
    def descricao_resumida(self, obj):
        texto = obj.descricao_evento
        return texto if len(texto) <= 60 else texto[:57] + "..."

    @admin.display(description="Situação financeira")
    def situacao(self, obj):
        return obj.situacao_financeira_display if obj.pk else "—"
