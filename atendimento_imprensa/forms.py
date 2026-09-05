"""Formulários do módulo de Atendimento à Imprensa.

Horários aceitam "17h03", "16h" ou "17:03". Um veículo ainda não cadastrado
pode ser informado direto no atendimento (campo "outro veículo").
"""

from django import forms
from django.db.models import Q

from core.planilhas import FORMATOS_HORA, limpa, limpa_multilinha

from .models import Atendimento, Responsavel, SituacaoAtendimento, Veiculo


class CampoHora(forms.TimeField):
    def __init__(self, **kwargs):
        kwargs.setdefault("input_formats", FORMATOS_HORA)
        kwargs.setdefault("required", False)
        kwargs.setdefault("widget", forms.TextInput(attrs={"placeholder": "hh:mm"}))
        super().__init__(**kwargs)


def _queryset_responsaveis(atual_pk=None):
    qs = Responsavel.objects.filter(ativo=True)
    if atual_pk:
        qs = qs | Responsavel.objects.filter(pk=atual_pk)
    return qs.distinct().order_by("nome")


class AtendimentoForm(forms.ModelForm):
    horario = CampoHora(label="Horário do pedido")
    horario_resposta = CampoHora(label="Horário da resposta")
    veiculo_novo = forms.CharField(
        label="Outro veículo (não listado)",
        required=False,
        max_length=150,
        help_text="Preencha só se o veículo ainda não estiver no cadastro.",
    )

    class Meta:
        model = Atendimento
        fields = [
            "data",
            "horario",
            "jornalista",
            "veiculo",
            "contato",
            "pedido",
            "situacao",
            "responsavel",
            "deadline",
            "horario_resposta",
            "responsavel_resposta",
            "fonte",
            "inicio_pedido",
            "final_pedido",
            "andamento",
            "resposta",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instancia = self.instance if self.instance.pk else None
        self.fields["responsavel"].queryset = _queryset_responsaveis(
            instancia and instancia.responsavel_id
        )
        self.fields["responsavel_resposta"].queryset = _queryset_responsaveis(
            instancia and instancia.responsavel_resposta_id
        )
        self.fields["veiculo"].queryset = Veiculo.objects.filter(
            Q(ativo=True) | Q(pk=instancia.veiculo_id if instancia else None)
        ).distinct().order_by("nome")
        self.fields["veiculo"].required = False
        self.fields["jornalista"].required = True
        self.fields["pedido"].required = True
        self.fields["data"].required = True

    def clean_veiculo_novo(self):
        return limpa(self.cleaned_data.get("veiculo_novo"))

    def clean(self):
        dados = super().clean()
        nova = dados.get("veiculo_novo")
        if nova:
            existente = Veiculo.objects.filter(nome__iexact=nova).first()
            if existente:
                if not existente.ativo:
                    existente.ativo = True
                    existente.save(update_fields=["ativo", "atualizado_em"])
                dados["veiculo"] = existente
            else:
                dados["veiculo"] = Veiculo.objects.create(nome=nova)
        data = dados.get("data")
        deadline = dados.get("deadline")
        if data and deadline and deadline < data:
            self.add_error(
                "deadline", "O deadline não pode ser anterior à data do pedido."
            )
        if dados.get("situacao") == SituacaoAtendimento.ATENDIDO and not (
            dados.get("resposta") or dados.get("andamento")
        ):
            self.add_error(
                "resposta",
                "Registre a resposta enviada (ou o andamento) ao marcar como atendido.",
            )
        for campo in ("jornalista", "contato"):
            if dados.get(campo):
                dados[campo] = limpa(dados[campo])
        for campo in ("pedido", "fonte", "inicio_pedido", "final_pedido", "andamento", "resposta"):
            if dados.get(campo):
                dados[campo] = limpa_multilinha(dados[campo])
        return dados


class FiltroAtendimentosForm(forms.Form):
    q = forms.CharField(required=False, label="Busca")
    situacao = forms.ChoiceField(
        required=False,
        label="Situação",
        choices=[("", "Todas")] + list(SituacaoAtendimento.choices),
    )
    veiculo = forms.ModelChoiceField(
        required=False, label="Veículo", queryset=Veiculo.objects.all()
    )
    responsavel = forms.ModelChoiceField(
        required=False, label="Responsável", queryset=Responsavel.objects.all()
    )
    inicio = forms.DateField(required=False, label="Pedidos a partir de")
    fim = forms.DateField(required=False, label="Pedidos até")


class ResponsavelForm(forms.ModelForm):
    class Meta:
        model = Responsavel
        fields = ("nome", "ativo")


class VeiculoForm(forms.ModelForm):
    class Meta:
        model = Veiculo
        fields = ("nome", "ativo")
