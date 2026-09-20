from django.contrib import admin

from .models import AcaoPendente, Conversa, Mensagem


class MensagemInline(admin.TabularInline):
    model = Mensagem
    extra = 0
    readonly_fields = ("autor", "texto", "ferramenta", "criado_em")
    can_delete = False


@admin.register(Conversa)
class ConversaAdmin(admin.ModelAdmin):
    list_display = ("pk", "usuario", "canal", "atualizado_em")
    list_filter = ("canal",)
    search_fields = ("usuario__username", "mensagens__texto")
    inlines = [MensagemInline]


@admin.register(AcaoPendente)
class AcaoPendenteAdmin(admin.ModelAdmin):
    list_display = ("pk", "ferramenta", "status", "resolvido_por", "resolvido_em")
    list_filter = ("status", "ferramenta")
    readonly_fields = ("rascunho", "resultado")
