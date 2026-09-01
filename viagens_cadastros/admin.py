from django.contrib import admin

from .models import Cargo, Combustivel, Servidor, TabelaDiaria, Unidade, Viatura


@admin.register(Unidade)
class UnidadeAdmin(admin.ModelAdmin):
    list_display = ("nome", "sigla", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome", "sigla")


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ("nome", "is_padrao", "ativo", "atualizado_em")
    list_filter = ("ativo", "is_padrao")
    search_fields = ("nome",)


@admin.register(Combustivel)
class CombustivelAdmin(admin.ModelAdmin):
    list_display = ("nome", "is_padrao", "ativo", "atualizado_em")
    list_filter = ("ativo", "is_padrao")
    search_fields = ("nome",)


@admin.register(Servidor)
class ServidorAdmin(admin.ModelAdmin):
    list_display = ("nome", "cargo", "unidade", "cpf_formatado", "status", "ativo")
    list_filter = ("ativo", "status", "cargo", "unidade")
    search_fields = ("nome", "cpf", "rg")
    list_select_related = ("cargo", "unidade")
    readonly_fields = ("status", "sem_rg", "legado_origem", "legado_pk")


@admin.register(Viatura)
class ViaturaAdmin(admin.ModelAdmin):
    list_display = ("placa", "modelo", "tipo", "unidade", "status", "ativo")
    list_filter = ("ativo", "status", "tipo", "combustivel", "unidade")
    search_fields = ("placa", "modelo")
    list_select_related = ("combustivel", "unidade")
    filter_horizontal = ("motoristas",)
    readonly_fields = ("status",)


@admin.register(TabelaDiaria)
class TabelaDiariaAdmin(admin.ModelAdmin):
    list_display = ("faixa", "vigencia_inicio", "valor_24h", "valor_15", "valor_30")
    list_filter = ("faixa",)
    # Derivados de `valor_24h` no `save()`: editá-los aqui daria a impressão de
    # que o valor gravado é o digitado.
    readonly_fields = ("valor_15", "valor_30")
