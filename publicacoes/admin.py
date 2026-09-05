from django.contrib import admin

from .models import Publicacao, Responsavel, Unidade


@admin.register(Responsavel)
class ResponsavelAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(Unidade)
class UnidadeAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(Publicacao)
class PublicacaoAdmin(admin.ModelAdmin):
    list_display = (
        "data", "titulo", "jornalista", "unidade", "status", "data_publicacao",
    )
    list_filter = ("status", "jornalista", "revisao", "enviado_sesp", "publicado_aen")
    search_fields = ("titulo", "fonte", "unidade__nome", "link_site")
    date_hierarchy = "data"
    autocomplete_fields = ("unidade",)
    readonly_fields = ("chave_importacao", "criado_em", "atualizado_em")
