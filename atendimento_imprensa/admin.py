from django.contrib import admin

from .models import Atendimento, Responsavel, Veiculo


@admin.register(Responsavel)
class ResponsavelAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(Veiculo)
class VeiculoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(Atendimento)
class AtendimentoAdmin(admin.ModelAdmin):
    list_display = (
        "data", "horario", "jornalista", "veiculo", "situacao", "responsavel", "deadline",
    )
    list_filter = ("situacao", "responsavel", "veiculo")
    search_fields = ("jornalista", "pedido", "resposta", "fonte", "contato")
    date_hierarchy = "data"
    autocomplete_fields = ("veiculo",)
    readonly_fields = ("chave_importacao", "criado_em", "atualizado_em")
