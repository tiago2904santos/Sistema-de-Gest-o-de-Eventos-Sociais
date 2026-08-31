from django.contrib import admin

from .models import LogAuditoria, RegistroAuditoria


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("acao", "usuario", "criado_em")
    list_filter = ("acao",)
    search_fields = ("acao", "descricao")
    readonly_fields = ("usuario", "acao", "descricao", "criado_em")


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("acao", "modelo", "objeto_repr", "usuario", "criado_em")
    list_filter = ("acao", "modelo")
    search_fields = ("modelo", "objeto_id", "objeto_repr")
    readonly_fields = (
        "usuario",
        "acao",
        "modelo",
        "objeto_id",
        "objeto_repr",
        "alteracoes",
        "caminho_requisicao",
        "criado_em",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
