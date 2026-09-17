"""Formulários dos catálogos do plano de trabalho, no modal dos cadastros.

Programa solicitante, horário de atendimento, atividade e preset — os quatro
sem Ativo nem Ordem, como manda a regra dos cadastros. O código da atividade
nasce do nome; o horário é digitado como início e fim e gravado como faixa.
"""

from django import forms

from .models import (
    AtividadePlanoTrabalho,
    HorarioAtendimento,
    PresetAtividadesPlanoTrabalho,
    ProgramaSolicitante,
)


class ProgramaSolicitanteForm(forms.ModelForm):
    class Meta:
        model = ProgramaSolicitante
        fields = ["nome"]
        labels = {"nome": "Nome do programa"}
        widgets = {"nome": forms.TextInput(attrs={"placeholder": "Ex.: PCPR NA COMUNIDADE", "data-uppercase": "true"})}


class HorarioAtendimentoForm(forms.ModelForm):
    horario_inicio = forms.TimeField(label="Horário de início", input_formats=["%H:%M"], widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}))
    horario_fim = forms.TimeField(label="Horário de fim", input_formats=["%H:%M"], widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}))

    class Meta:
        model = HorarioAtendimento
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        faixa = getattr(self.instance, "faixa", "") or ""
        if faixa and not self.is_bound:
            inicio, _, fim = faixa.partition(" até ")
            self.initial.setdefault("horario_inicio", inicio.strip())
            self.initial.setdefault("horario_fim", fim.strip())

    def clean(self):
        cleaned = super().clean()
        inicio, fim = cleaned.get("horario_inicio"), cleaned.get("horario_fim")
        if inicio and fim:
            faixa = f"{inicio:%H:%M} até {fim:%H:%M}"
            if HorarioAtendimento.objects.filter(faixa=faixa).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError("Já existe um horário com essa faixa.")
            self.instance.faixa = faixa
        return cleaned


class AtividadePlanoTrabalhoForm(forms.ModelForm):
    class Meta:
        model = AtividadePlanoTrabalho
        fields = ["nome", "recurso_necessario", "meta"]
        labels = {"nome": "Atividade", "recurso_necessario": "Recursos necessários", "meta": "Metas"}
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Nome da atividade"}),
            "recurso_necessario": forms.Textarea(attrs={"rows": 3, "placeholder": "Recursos necessários para a atividade"}),
            "meta": forms.Textarea(attrs={"rows": 3, "placeholder": "Meta exibida no documento"}),
        }

    def _gerar_codigo_unico(self, nome):
        base = AtividadePlanoTrabalho.codigo_de(nome) or "ATIVIDADE"
        codigo, n = base, 1
        while AtividadePlanoTrabalho.objects.filter(codigo=codigo).exclude(pk=self.instance.pk).exists():
            n += 1
            codigo = f"{base}_{n}"
        return codigo

    def save(self, commit=True):
        if not self.instance.codigo:
            self.instance.codigo = self._gerar_codigo_unico(self.cleaned_data.get("nome", ""))
        return super().save(commit=commit)


class PresetAtividadesForm(forms.ModelForm):
    def _get_validation_exclusions(self):
        # A troca de padrão é validada e gravada pelo save do catálogo.
        return super()._get_validation_exclusions() | {"is_padrao"}

    class Meta:
        model = PresetAtividadesPlanoTrabalho
        fields = ["nome", "atividades", "is_padrao"]
        labels = {"nome": "Nome do preset", "atividades": "Atividades", "is_padrao": "Usar como padrão"}
        help_texts = {"is_padrao": "Vem escolhido em todo plano de trabalho novo."}
        widgets = {"nome": forms.TextInput(attrs={"placeholder": "Ex.: PCPR NA COMUNIDADE", "data-uppercase": "true"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["atividades"].queryset = AtividadePlanoTrabalho.objects.order_by("nome")
        self.fields["atividades"].required = True
        self.fields["atividades"].error_messages["required"] = "Selecione ao menos uma atividade."
