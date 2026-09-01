"""Formulários do roteiro: os dados gerais e os trechos percorridos.

O roteiro é montado trecho a trecho, e é dos trechos que sai o cálculo das
diárias — cada um informa para onde se vai, quando se sai e quando se chega.
Por isso o formulário principal guarda pouca coisa (sede, equipe, vínculo) e o
conjunto de trechos carrega o essencial.
"""

from django import forms
from django.forms import inlineformset_factory

from cadastros.models import Municipio
from solicitacoes.models import SolicitacaoEvento

from .models import Roteiro, RoteiroTrecho


class EntradaDataHora(forms.DateTimeInput):
    """Campo nativo de data e hora do navegador.

    O formato ISO é o que o ``datetime-local`` envia e espera de volta; sem
    declará-lo nos ``input_formats``, editar um roteiro existente traria o
    campo vazio.
    """

    input_type = "datetime-local"

    def __init__(self, attrs=None):
        super().__init__(attrs={"class": "form-controle", **(attrs or {})},
                         format="%Y-%m-%dT%H:%M")


FORMATOS_DATA_HORA = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"]

# O mesmo rótulo que `components/select.html` usa nas demais telas.
PLACEHOLDER_SELECT = "Selecione..."


def _municipios_ativos():
    return Municipio.objects.filter(ativo=True).select_related("estado")


def _vestir(form):
    """Deixa os campos com a cara do resto do sistema.

    Sem isto o navegador desenha os controles nativos no meio de uma tela
    estilizada, e o Django rotula a opção vazia em inglês — "Select an
    option" — enquanto todas as outras telas dizem "Selecione...".
    """
    for campo in form.fields.values():
        classes = campo.widget.attrs.get("class", "").split()
        if "form-controle" not in classes:
            classes.append("form-controle")
        campo.widget.attrs["class"] = " ".join(classes)
        if isinstance(campo, forms.ModelChoiceField):
            campo.empty_label = PLACEHOLDER_SELECT


class RoteiroForm(forms.ModelForm):
    class Meta:
        model = Roteiro
        fields = [
            "origem_municipio",
            "quantidade_servidores",
            "solicitacao",
            "observacoes",
        ]
        labels = {"origem_municipio": "município sede"}
        help_texts = {
            "origem_municipio": "De onde a equipe sai e para onde volta.",
            "quantidade_servidores": "O total das diárias é multiplicado por este número.",
            "solicitacao": "Opcional: vincula o roteiro a uma solicitação de evento.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["origem_municipio"].queryset = _municipios_ativos()
        self.fields["solicitacao"].queryset = SolicitacaoEvento.objects.order_by(
            "-data_solicitacao", "-pk"
        )
        self.fields["solicitacao"].required = False
        # `clean_quantidade_servidores` recusa zero; deixar o `min` do HTML em 0
        # faria o navegador aceitar um valor que o servidor devolve com erro.
        self.fields["quantidade_servidores"].widget.attrs["min"] = 1
        _vestir(self)

    def clean_quantidade_servidores(self):
        quantidade = self.cleaned_data.get("quantidade_servidores")
        if quantidade is not None and quantidade < 1:
            raise forms.ValidationError("Informe ao menos um servidor.")
        return quantidade

    def save(self, commit=True):
        roteiro = super().save(commit=False)
        # O tipo acompanha o vínculo: quem nasce ligado a uma solicitação é
        # roteiro de evento, o resto é avulso.
        roteiro.tipo = (
            Roteiro.Tipo.EVENTO if roteiro.solicitacao_id else Roteiro.Tipo.AVULSO
        )
        if commit:
            roteiro.save()
        return roteiro


class RoteiroTrechoForm(forms.ModelForm):
    class Meta:
        model = RoteiroTrecho
        fields = [
            "ordem",
            "origem_municipio",
            "destino_municipio",
            "saida_dt",
            "chegada_dt",
            "distancia_km",
        ]
        widgets = {
            "saida_dt": EntradaDataHora(),
            "chegada_dt": EntradaDataHora(),
        }

    # `ordem` tem default=1, então o navegador desenha as linhas extras já
    # preenchidas. Mexer só nesse número faz o Django considerar a linha
    # alterada e gravá-la — um trecho sem destino nem datas, que o motor
    # ignora e a tela de detalhe mostra como uma fileira de traços.
    CAMPOS_DE_CONTEUDO = (
        "origem_municipio",
        "destino_municipio",
        "saida_dt",
        "chegada_dt",
        "distancia_km",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ("saida_dt", "chegada_dt"):
            self.fields[nome].input_formats = FORMATOS_DATA_HORA
        for nome in ("origem_municipio", "destino_municipio"):
            self.fields[nome].queryset = _municipios_ativos()
        self.fields["ordem"].widget.attrs["min"] = 1
        self.fields["distancia_km"].widget.attrs.update({"step": "0.01", "min": 0})
        _vestir(self)

    def esta_em_branco(self):
        """Linha sem nenhum dado além da ordem — a tela promete ignorá-la."""
        return not any(self.cleaned_data.get(nome) for nome in self.CAMPOS_DE_CONTEUDO)

    def clean(self):
        dados = super().clean()
        if dados.get("DELETE"):
            return dados
        if self.esta_em_branco():
            if self.instance.pk:
                # Apagar sozinho um trecho já gravado seria destrutivo demais
                # para um campo esvaziado sem querer: para isso existe o
                # "Remover" da linha.
                self.add_error(
                    None,
                    "Trecho sem dados. Preencha o trecho ou marque \u201cRemover\u201d.",
                )
                return dados
            dados["DELETE"] = True
            return dados
        saida, chegada = dados.get("saida_dt"), dados.get("chegada_dt")
        if saida and chegada and chegada < saida:
            self.add_error(
                "chegada_dt", "A chegada não pode ser anterior à saída do trecho."
            )
        # Trecho sem destino não entra no cálculo; é melhor recusar na tela do
        # que gravar uma linha que o motor vai ignorar em silêncio.
        if dados.get("saida_dt") and not dados.get("destino_municipio"):
            self.add_error("destino_municipio", "Informe o destino do trecho.")
        return dados


class BaseTrechoFormSet(forms.BaseInlineFormSet):
    """Numera as linhas novas em sequência.

    `ordem` tem `default=1`, então sem isto o formulário abre com "1" em todas
    as linhas extras — e preencher duas sem tocar no número, que é o caminho
    natural, esbarra na unicidade de (roteiro, ordem) já no primeiro envio.
    """

    def add_fields(self, form, index):
        super().add_fields(form, index)
        if index is not None and index >= self.initial_form_count():
            form.fields["ordem"].initial = index + 1


TrechoFormSet = inlineformset_factory(
    Roteiro,
    RoteiroTrecho,
    form=RoteiroTrechoForm,
    formset=BaseTrechoFormSet,
    extra=3,
    can_delete=True,
    min_num=0,
    validate_min=False,
)
