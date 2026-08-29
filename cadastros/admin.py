from django.contrib import admin

from .models import (
    Estado,
    Equipe,
    Motorista,
    Municipio,
    OrgaoResponsavel,
    Regiao,
    Servico,
    TipoEvento,
)


class CadastroBaseAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(TipoEvento)
class TipoEventoAdmin(CadastroBaseAdmin):
    pass


@admin.register(Servico)
class ServicoAdmin(CadastroBaseAdmin):
    pass


@admin.register(Equipe)
class EquipeAdmin(CadastroBaseAdmin):
    pass


@admin.register(OrgaoResponsavel)
class OrgaoResponsavelAdmin(CadastroBaseAdmin):
    pass


@admin.register(Regiao)
class RegiaoAdmin(CadastroBaseAdmin):
    pass


@admin.register(Estado)
class EstadoAdmin(CadastroBaseAdmin):
    list_display = ("nome", "sigla", "codigo_ibge", "ativo", "atualizado_em")


@admin.register(Municipio)
class MunicipioAdmin(CadastroBaseAdmin):
    list_display = ("nome", "estado", "regiao", "ativo", "atualizado_em")
    list_filter = ("ativo", "estado", "regiao")


@admin.register(Motorista)
class MotoristaAdmin(CadastroBaseAdmin):
    list_display = ("nome", "telefone", "ativo", "atualizado_em")
