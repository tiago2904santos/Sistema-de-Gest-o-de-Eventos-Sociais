from django.contrib import admin

from .models import LogAuditoria


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("acao", "usuario", "criado_em")
    list_filter = ("acao",)
    search_fields = ("acao", "descricao")
    readonly_fields = ("usuario", "acao", "descricao", "criado_em")
