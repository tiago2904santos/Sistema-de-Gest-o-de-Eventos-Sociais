from django.contrib import admin

from .models import (
    AcaoPendente,
    Conversa,
    Mensagem,
    MensagemEnviada,
    MensagemRecebida,
    VinculoWhatsApp,
)


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


@admin.register(VinculoWhatsApp)
class VinculoWhatsAppAdmin(admin.ModelAdmin):
    """Onde um número é autorizado a falar pelo sistema.

    É a única superfície de cadastro do canal, e de propósito: vincular um
    número é decisão administrativa, com nome e data, não autoatendimento.
    """

    list_display = ("numero", "usuario", "ativo", "ultima_entrada_em", "autorizado_por")
    list_filter = ("ativo",)
    search_fields = ("numero", "usuario__username", "usuario__first_name")
    readonly_fields = ("ultima_entrada_em", "criado_em")

    def save_model(self, request, obj, form, change):
        if not obj.autorizado_por_id:
            obj.autorizado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(MensagemRecebida)
class MensagemRecebidaAdmin(admin.ModelAdmin):
    list_display = ("recebida_em", "numero", "tipo", "status", "wa_message_id")
    list_filter = ("status", "tipo")
    search_fields = ("numero", "texto", "wa_message_id")
    readonly_fields = [c.name for c in MensagemRecebida._meta.fields]


@admin.register(MensagemEnviada)
class MensagemEnviadaAdmin(admin.ModelAdmin):
    list_display = ("criada_em", "numero", "status", "tentativas", "enviada_em")
    list_filter = ("status",)
    search_fields = ("numero", "texto")
    readonly_fields = ("wa_message_id", "enviada_em", "criada_em")
