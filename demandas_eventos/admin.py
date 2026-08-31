from django.contrib import admin

from .models import DemandaEvento, Palestrante, RespostaPadrao, Tema


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
    list_display = (
        "id", "data_solicitacao", "tipo_evento", "municipio", "solicitante", "status"
    )
    list_filter = ("status", "tipo_evento", "tema", "setores")
    search_fields = (
        "solicitante", "contato", "descricao", "pedido_contato", "assunto_email"
    )
    date_hierarchy = "data_solicitacao"
    filter_horizontal = ("palestrantes", "setores")
    readonly_fields = ("origem_importacao", "chave_importacao", "criado_em", "atualizado_em")
