from django.contrib import admin

from .models import (
    DemandaEvento,
    HistoricoDemanda,
    Palestrante,
    RespostaPadrao,
    Tema,
)


class HistoricoDemandaInline(admin.TabularInline):
    model = HistoricoDemanda
    extra = 0
    can_delete = False
    readonly_fields = (
        "usuario", "acao", "status_anterior", "status_novo", "descricao", "criado_em"
    )


@admin.register(Tema)
class TemaAdmin(admin.ModelAdmin):
    list_display = ("nome", "atualizado_em")
    search_fields = ("nome",)


@admin.register(Palestrante)
class PalestranteAdmin(admin.ModelAdmin):
    list_display = ("nome", "municipio", "divisao", "lotacao")
    list_filter = ("municipio", "divisao")
    search_fields = ("nome", "lotacao", "contato", "email")


@admin.register(RespostaPadrao)
class RespostaPadraoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "atualizado_em")
    search_fields = ("tipo", "mensagem")


@admin.register(DemandaEvento)
class DemandaEventoAdmin(admin.ModelAdmin):
    list_display = (
        "id", "data_solicitacao", "evento", "municipio", "solicitante", "status"
    )
    list_filter = ("status", "evento", "tema", "setores")
    search_fields = (
        "solicitante", "contato", "descricao", "pedido_contato", "assunto_email"
    )
    date_hierarchy = "data_solicitacao"
    filter_horizontal = ("setores",)
    readonly_fields = (
        "origem_importacao", "chave_importacao", "criado_em", "atualizado_em"
    )
    inlines = (HistoricoDemandaInline,)
