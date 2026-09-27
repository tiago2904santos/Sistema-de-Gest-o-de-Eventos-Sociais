from django.contrib import admin

from .models import Feriado


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    """Feriados locais (estaduais, municipais, pontos facultativos). Os nacionais são calculados."""

    list_display = ("data", "nome", "anual", "municipio")
    list_filter = ("anual",)
    search_fields = ("nome", "municipio__nome")
    autocomplete_fields = ("municipio",)
