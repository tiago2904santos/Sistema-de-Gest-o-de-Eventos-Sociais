from django.contrib import admin

from .models import Roteiro, RoteiroDestino, RoteiroDiariaComponente, RoteiroTrecho


class RoteiroDestinoInline(admin.TabularInline):
    model = RoteiroDestino
    extra = 0


class RoteiroTrechoInline(admin.TabularInline):
    model = RoteiroTrecho
    extra = 0


class ComponenteInline(admin.TabularInline):
    model = RoteiroDiariaComponente
    extra = 0
    # A composição explica um pagamento: consulta-se, não se edita.
    can_delete = False
    readonly_fields = (
        "ordem", "origem", "faixa", "percentual", "quantidade",
        "valor_unitario", "subtotal", "tabela_diaria", "tabela_vigencia_inicio",
        "periodo_inicio", "periodo_fim",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Roteiro)
class RoteiroAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo", "status", "origem_municipio", "valor_diarias", "cancelado")
    list_filter = ("status", "tipo", "cancelado")
    search_fields = ("observacoes",)
    list_select_related = ("origem_municipio",)
    inlines = [RoteiroDestinoInline, RoteiroTrechoInline, ComponenteInline]
