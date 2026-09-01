"""Formulários do roteiro: os dados gerais e os trechos percorridos.

O roteiro é montado trecho a trecho, e é dos trechos que sai o cálculo das
diárias — cada um informa para onde se vai, quando se sai e quando se chega.
Por isso o formulário principal guarda pouca coisa (sede, equipe, vínculo) e o
conjunto de trechos carrega o essencial.
"""

from datetime import datetime

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from cadastros.models import Municipio
from solicitacoes.models import SolicitacaoEvento

from .models import Roteiro, RoteiroDestino, RoteiroTrecho

FORMATOS_DATA = ["%Y-%m-%d", "%d/%m/%Y"]

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
    """Sede e vínculo do roteiro — o percurso vem dos formsets.

    ``quantidade_servidores`` e ``observacoes`` ficam de fora por decisão do
    dono do produto (01/09/2026): a tela não os oferece. Deixá-los no
    formulário faria a edição gravar o vazio por cima do que está no banco;
    fora dele, o valor guardado é preservado — e roteiro novo nasce com o
    padrão do modelo (um servidor).
    """

    class Meta:
        model = Roteiro
        fields = [
            "origem_municipio",
            "solicitacao",
        ]
        labels = {"origem_municipio": "município sede"}
        help_texts = {
            "origem_municipio": "De onde a equipe sai e para onde volta.",
            "solicitacao": "Opcional: vincula o roteiro a uma solicitação de evento.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["origem_municipio"].queryset = _municipios_ativos()
        self.fields["solicitacao"].queryset = SolicitacaoEvento.objects.order_by(
            "-data_solicitacao", "-pk"
        )
        self.fields["solicitacao"].required = False
        _vestir(self)

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
    """Um deslocamento do percurso, com data e hora separadas.

    O par data + hora segue a organização do editor de referência: a data usa
    o calendário do design system e a hora fica num campo próprio. Os dois são
    compostos em ``saida_dt``/``chegada_dt`` na validação.
    """

    saida_data = forms.DateField(
        label="Data de saída", required=False, input_formats=FORMATOS_DATA
    )
    saida_hora = forms.TimeField(label="Hora de saída", required=False)
    chegada_data = forms.DateField(
        label="Data de chegada", required=False, input_formats=FORMATOS_DATA
    )
    chegada_hora = forms.TimeField(label="Hora de chegada", required=False)

    class Meta:
        model = RoteiroTrecho
        fields = [
            "ordem",
            "sentido",
            "origem_municipio",
            "destino_municipio",
            "distancia_km",
            "duracao_min",
        ]

    # `ordem` tem default=1, então o navegador desenha as linhas extras já
    # preenchidas. Mexer só nesse número faz o Django considerar a linha
    # alterada e gravá-la — um trecho sem destino nem datas, que o motor
    # ignora e a tela de detalhe mostra como uma fileira de traços.
    CAMPOS_DE_CONTEUDO = (
        "origem_municipio",
        "destino_municipio",
        "saida_data",
        "saida_hora",
        "chegada_data",
        "chegada_hora",
        "distancia_km",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ("origem_municipio", "destino_municipio"):
            self.fields[nome].queryset = _municipios_ativos()
        # Preenchidos pela tela (rota e tempos), nunca digitados: um POST sem
        # eles cai nos defaults do modelo em vez de derrubar o formulário.
        self.fields["sentido"].required = False
        self.fields["duracao_min"].required = False
        if self.instance.pk:
            for prefixo in ("saida", "chegada"):
                instante = getattr(self.instance, f"{prefixo}_dt")
                if instante:
                    local = timezone.localtime(instante)
                    self.initial.setdefault(f"{prefixo}_data", local.date())
                    self.initial.setdefault(
                        f"{prefixo}_hora",
                        local.time().replace(second=0, microsecond=0),
                    )

    def _compor_instante(self, dados, prefixo, rotulo):
        data = dados.get(f"{prefixo}_data")
        hora = dados.get(f"{prefixo}_hora")
        if data and not hora:
            self.add_error(f"{prefixo}_hora", f"Informe a hora de {rotulo}.")
            return None
        if hora and not data:
            self.add_error(f"{prefixo}_data", f"Informe a data de {rotulo}.")
            return None
        if not data:
            return None
        return timezone.make_aware(datetime.combine(data, hora))

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
        if not dados.get("sentido"):
            dados["sentido"] = RoteiroTrecho.Sentido.IDA
            self.instance.sentido = RoteiroTrecho.Sentido.IDA
        saida = self._compor_instante(dados, "saida", "saída")
        chegada = self._compor_instante(dados, "chegada", "chegada")
        if saida and chegada and chegada < saida:
            self.add_error(
                "chegada_hora", "A chegada não pode ser anterior à saída do trecho."
            )
        # Trecho sem destino não entra no cálculo; é melhor recusar na tela do
        # que gravar uma linha que o motor vai ignorar em silêncio.
        if saida and not dados.get("destino_municipio"):
            self.add_error("destino_municipio", "Informe o destino do trecho.")
        # Fora de Meta.fields, os instantes não passam pelo construtor do
        # ModelForm: a instância recebe o valor composto aqui.
        self.instance.saida_dt = saida
        self.instance.chegada_dt = chegada
        return dados


# `extra=1`: um slot em branco para a tela revelar de saída; os demais cards
# nascem do <template> com o empty_form, clonados pelo roteiro-editor.js
# (DS.aprimorar liga os componentes). Slot em branco é ignorado na gravação.
TrechoFormSet = inlineformset_factory(
    Roteiro,
    RoteiroTrecho,
    form=RoteiroTrechoForm,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


class RoteiroDestinoForm(forms.ModelForm):
    """Uma linha de destino — o percurso nasce daqui, na ordem da visita."""

    class Meta:
        model = RoteiroDestino
        fields = ["ordem", "municipio"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["municipio"].queryset = _municipios_ativos()
        self.fields["municipio"].required = False

    def clean(self):
        dados = super().clean()
        if dados.get("DELETE"):
            return dados
        # Linha vazia é slot da tela: some na gravação, sem alarde.
        if not dados.get("municipio"):
            dados["DELETE"] = True
        return dados


DestinoFormSet = inlineformset_factory(
    Roteiro,
    RoteiroDestino,
    form=RoteiroDestinoForm,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)
