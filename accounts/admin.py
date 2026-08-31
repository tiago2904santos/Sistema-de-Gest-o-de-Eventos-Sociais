from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Modulo, Setor, User


class UsuarioAdmin(UserAdmin):
    filter_horizontal = UserAdmin.filter_horizontal + ("setores",)
    fieldsets = UserAdmin.fieldsets + (
        ("Setores", {"fields": ("setores",)}),
    )


@admin.register(Setor)
class SetorAdmin(admin.ModelAdmin):
    list_display = ("nome", "sigla", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome", "sigla")


@admin.register(Modulo)
class ModuloAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome", "codigo")
    filter_horizontal = ("setores",)


admin.site.register(User, UsuarioAdmin)
