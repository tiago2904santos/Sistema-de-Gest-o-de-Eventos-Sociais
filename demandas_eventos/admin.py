from django import forms
from django.contrib import admin

from .models import (
    DemandaEvento,
    HistoricoDemanda,
    Palestrante,
    RespostaPadrao,
    Tema,
)


class DemandaEventoAdminForm(forms.ModelForm):
    class Meta:
        model = DemandaEvento
        fields = "__all__"

    def clean_setores(self):
        setores = self.cleaned_data.get("setores")
        if not setores:
            raise forms.ValidationError("Selecione ao menos um setor envolvido.")
        return setores


class HistoricoDemandaInline(admin.TabularInline):
    model = HistoricoDemanda
    extra = 0
    can_delete = False
    readonly_fields = (
        "usuario", "acao", "status_anterior", "status_novo", "descricao", "criado_em"
    )


@admin.register(Tema)
class TemaAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(Palestrante)
class PalestranteAdmin(admin.ModelAdmin):
    list_display = ("nome", "municipio", "divisao", "lotacao", "ativo")
    list_filter = ("ativo", "municipio", "divisao")
    search_fields = ("nome", "lotacao", "contato", "email")
    filter_horizontal = ("temas",)


@admin.register(RespostaPadrao)
class RespostaPadraoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("tipo", "mensagem")


@admin.register(DemandaEvento)
class DemandaEventoAdmin(admin.ModelAdmin):
    form = DemandaEventoAdminForm
    list_display = (
        "id", "data_solicitacao", "tipo_evento", "municipio", "solicitante", "status"
    )
    list_filter = ("status", "tipo_evento", "tema", "setores")
    search_fields = (
        "solicitante", "contato", "descricao", "pedido_contato", "assunto_email"
    )
    date_hierarchy = "data_solicitacao"
    filter_horizontal = ("palestrantes", "setores")
    readonly_fields = (
        "status", "origem_importacao", "chave_importacao", "criado_em", "atualizado_em"
    )
    inlines = (HistoricoDemandaInline,)
