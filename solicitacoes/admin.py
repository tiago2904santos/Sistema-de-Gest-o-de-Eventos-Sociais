from django.contrib import admin

from .models import (
    HistoricoSolicitacao,
    SolicitacaoEvento,
    SolicitacaoEventoEquipe,
    SolicitacaoEventoServico,
)


class SolicitacaoEventoServicoInline(admin.TabularInline):
    model = SolicitacaoEventoServico
    extra = 0


class SolicitacaoEventoEquipeInline(admin.TabularInline):
    model = SolicitacaoEventoEquipe
    extra = 0


@admin.register(SolicitacaoEvento)
class SolicitacaoEventoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "municipio",
        "regiao",
        "tipo_evento",
        "data_inicio_evento",
        "status",
        "decisao_dg",
    )
    list_filter = ("status", "decisao_dg", "regiao", "tipo_evento")
    search_fields = ("solicitante_nome", "local_evento", "municipio__nome")
    date_hierarchy = "data_inicio_evento"
    inlines = [SolicitacaoEventoServicoInline, SolicitacaoEventoEquipeInline]
    readonly_fields = (
        "regiao",
        "quantidade_servidores",
        "decidido_por",
        "decidido_em",
        "criado_em",
        "atualizado_em",
    )


@admin.register(HistoricoSolicitacao)
class HistoricoSolicitacaoAdmin(admin.ModelAdmin):
    list_display = ("solicitacao", "acao", "status_anterior", "status_novo", "usuario", "criado_em")
    list_filter = ("acao", "status_novo")
    readonly_fields = (
        "solicitacao",
        "usuario",
        "acao",
        "status_anterior",
        "status_novo",
        "observacao",
        "criado_em",
    )
