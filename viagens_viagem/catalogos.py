"""Formulário do catálogo de tipos de viagem, no modal dos cadastros."""

from django import forms

from .models import TipoViagem


class TipoViagemForm(forms.ModelForm):
    class Meta:
        model = TipoViagem
        fields = ["nome"]
        labels = {"nome": "Nome"}
        widgets = {"nome": forms.TextInput(attrs={"placeholder": "Ex.: PCPR na Comunidade"})}
