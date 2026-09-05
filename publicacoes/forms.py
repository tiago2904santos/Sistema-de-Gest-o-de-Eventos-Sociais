"""Formulários do módulo de Publicações.

Horários aceitam a grafia da planilha ("17h03", "16h") além de "17:03".
Unidades novas podem ser informadas direto no formulário da pauta: o
campo "outra unidade" cria o cadastro na hora, sem passar pelo admin.
"""

from django import forms
from django.db.models import Q

from core.planilhas import FORMATOS_HORA, limpa

from .models import Publicacao, Responsavel, StatusPublicacao, Unidade

OPCOES_SIM_NAO = [("", "—"), ("1", "Sim"), ("0", "Não")]


class CampoHora(forms.TimeField):
    def __init__(self, **kwargs):
        kwargs.setdefault("input_formats", FORMATOS_HORA)
        kwargs.setdefault("required", False)
        kwargs.setdefault("widget", forms.TextInput(attrs={"placeholder": "hh:mm"}))
        super().__init__(**kwargs)


class CampoSimNao(forms.NullBooleanField):
    """Sim/Não/— com valores "1"/"0"/"" (compatível com o select do sistema)."""

    widget = forms.Select(choices=OPCOES_SIM_NAO)

    def to_python(self, value):
        if value in ("1", 1, True, "True", "true"):
            return True
        if value in ("0", 0, False, "False", "false"):
            return False
        return None

    def prepare_value(self, value):
        if value in (True, "1", "True", "true"):
            return "1"
        if value in (False, "0", "False", "false"):
            return "0"
        return ""


def _queryset_responsaveis(atual_pk=None):
    qs = Responsavel.objects.filter(ativo=True)
    if atual_pk:
        qs = qs | Responsavel.objects.filter(pk=atual_pk)
    return qs.distinct().order_by("nome")


class PublicacaoForm(forms.ModelForm):
    inicio_pauta = CampoHora(label="Início da pauta")
    colocada_edicao = CampoHora(label="Colocada para edição")
    horario_publicacao = CampoHora(label="Horário de publicação")
    bitly_grupos = CampoSimNao(label="Bitly nos grupos", required=False)
    enviado_sesp = CampoSimNao(label="Enviado para a SESP", required=False)
    publicado_aen = CampoSimNao(label="Publicado na AEN", required=False)
    unidade_nova = forms.CharField(
        label="Outra unidade (não listada)",
        required=False,
        max_length=150,
        help_text="Preencha só se a unidade ainda não estiver no cadastro.",
    )

    class Meta:
        model = Publicacao
        fields = [
            "data",
            "jornalista",
            "unidade",
            "fonte",
            "inicio_pauta",
            "titulo",
            "status",
            "andamento",
            "colocada_edicao",
            "data_publicacao",
            "horario_publicacao",
            "revisao",
            "galeria_fotos",
            "bitly_grupos",
            "enviado_sesp",
            "publicado_aen",
            "link_site",
            "link_aen",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instancia = self.instance if self.instance.pk else None
        self.fields["jornalista"].queryset = _queryset_responsaveis(
            instancia and instancia.jornalista_id
        )
        self.fields["revisao"].queryset = _queryset_responsaveis(
            instancia and instancia.revisao_id
        )
        self.fields["galeria_fotos"].queryset = _queryset_responsaveis(
            instancia and instancia.galeria_fotos_id
        )
        self.fields["unidade"].queryset = Unidade.objects.filter(
            Q(ativo=True) | Q(pk=instancia.unidade_id if instancia else None)
        ).distinct().order_by("nome")
        self.fields["unidade"].required = False
        self.fields["titulo"].required = True
        self.fields["data"].required = True

    def clean_unidade_nova(self):
        return limpa(self.cleaned_data.get("unidade_nova"))

    def clean(self):
        dados = super().clean()
        unidade = dados.get("unidade")
        nova = dados.get("unidade_nova")
        if nova:
            existente = Unidade.objects.filter(nome__iexact=nova).first()
            if existente:
                if not existente.ativo:
                    existente.ativo = True
                    existente.save(update_fields=["ativo", "atualizado_em"])
                dados["unidade"] = existente
            else:
                dados["unidade"] = Unidade.objects.create(nome=nova)
        elif not unidade:
            self.add_error(
                "unidade", "Escolha a unidade responsável ou informe uma nova."
            )
        status = dados.get("status")
        data_pub = dados.get("data_publicacao")
        data = dados.get("data")
        if status == StatusPublicacao.PUBLICADA and not data_pub:
            self.add_error(
                "data_publicacao", "Informe a data em que a pauta foi publicada."
            )
        if data and data_pub and data_pub < data:
            self.add_error(
                "data_publicacao",
                "A publicação não pode ser anterior à data da pauta.",
            )
        for campo in ("titulo", "fonte"):
            if dados.get(campo):
                dados[campo] = limpa(dados[campo])
        return dados


class FiltroPublicacoesForm(forms.Form):
    q = forms.CharField(required=False, label="Busca")
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[("", "Todos")] + list(StatusPublicacao.choices),
    )
    jornalista = forms.ModelChoiceField(
        required=False, label="Jornalista", queryset=Responsavel.objects.all()
    )
    unidade = forms.ModelChoiceField(
        required=False, label="Unidade", queryset=Unidade.objects.all()
    )
    inicio = forms.DateField(required=False, label="Pautas a partir de")
    fim = forms.DateField(required=False, label="Pautas até")


class ResponsavelForm(forms.ModelForm):
    class Meta:
        model = Responsavel
        fields = ("nome", "ativo")


class UnidadeForm(forms.ModelForm):
    class Meta:
        model = Unidade
        fields = ("nome", "ativo")
