"""Formulários dos cadastros de viagens.

A validação forte fica aqui, e não só no modelo: o operador precisa ver o erro
no campo certo. CPF e placa são validados por conteúdo (dígito verificador,
formato de placa) porque um cadastro errado vira documento oficial errado.
"""

from django import forms

from .models import Cargo, Combustivel, Servidor, TabelaDiaria, Unidade, Viatura
from .normalizacao import (
    RG_NAO_POSSUI,
    RG_NAO_POSSUI_EXIBICAO,
    cpf_valido,
    normalizar_digitos,
    normalizar_maiusculas,
    normalizar_placa,
    normalizar_rg,
    placa_valida,
)


def apenas_ativos(campo, vinculado_pk=None):
    """Restringe o select a registros ativos, sem esconder o já vinculado.

    A mensagem de erro de exclusão promete que inativar "retira das novas
    escolhas"; sem isto o registro inativo continuaria selecionável. Manter o
    que já está vinculado evita que abrir um cadastro antigo e salvar apague
    silenciosamente a escolha anterior.
    """
    queryset = campo.queryset.filter(ativo=True)
    if vinculado_pk:
        queryset = queryset | campo.queryset.filter(pk=vinculado_pk)
    campo.queryset = queryset.distinct()


class NomeNormalizadoMixin:
    """Normaliza o nome já na validação, e não só ao gravar.

    Os modelos deste app gravam o nome em maiúsculas com espaços colapsados.
    Se o formulário validasse o texto cru, a checagem de unicidade
    consultaria "Maria da Silva" enquanto o banco guarda "MARIA DA SILVA":
    nada seria encontrado, o formulário passaria e o `save()` estouraria em
    IntegrityError — erro 500 na cara do operador em vez de "já existe".
    """

    def clean_nome(self):
        return normalizar_maiusculas(self.cleaned_data.get("nome"))


class UnidadeForm(NomeNormalizadoMixin, forms.ModelForm):
    class Meta:
        model = Unidade
        fields = ["nome", "sigla", "ativo"]

    def clean_sigla(self):
        return normalizar_maiusculas(self.cleaned_data.get("sigla"))


class CargoForm(NomeNormalizadoMixin, forms.ModelForm):
    class Meta:
        model = Cargo
        fields = ["nome", "is_padrao", "ativo"]


class CombustivelForm(NomeNormalizadoMixin, forms.ModelForm):
    class Meta:
        model = Combustivel
        fields = ["nome", "is_padrao", "ativo"]


class ServidorForm(NomeNormalizadoMixin, forms.ModelForm):
    # Declarados à mão porque o modelo guarda **só dígitos** (11 caracteres),
    # e o `max_length` herdado validaria a entrada crua: quem colasse
    # "529.982.247-25" levaria "no máximo 11 caracteres" antes de o
    # `clean_cpf` ter chance de tirar a pontuação.
    cpf = forms.CharField(
        label="CPF",
        max_length=14,
        required=False,
        help_text="Pode digitar com ou sem pontuação.",
    )
    telefone = forms.CharField(
        label="telefone",
        max_length=16,
        required=False,
        help_text="Com DDD. Pode digitar com ou sem pontuação.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instancia = self.instance if self.instance and self.instance.pk else None
        apenas_ativos(self.fields["cargo"], instancia and instancia.cargo_id)
        apenas_ativos(self.fields["unidade"], instancia and instancia.unidade_id)

    class Meta:
        model = Servidor
        fields = ["nome", "cargo", "cpf", "rg", "telefone", "unidade", "ativo"]
        help_texts = {
            "rg": f'Deixe em branco ou escreva "{RG_NAO_POSSUI}" se não possuir.',
        }

    def clean_cpf(self):
        cpf = normalizar_digitos(self.cleaned_data.get("cpf"))
        if not cpf:
            return ""
        if len(cpf) != 11:
            raise forms.ValidationError("O CPF deve ter 11 dígitos.")
        if not cpf_valido(cpf):
            raise forms.ValidationError("CPF inválido: verifique os dígitos.")
        return cpf

    def clean_telefone(self):
        telefone = normalizar_digitos(self.cleaned_data.get("telefone"))
        if not telefone:
            return ""
        if len(telefone) not in (10, 11):
            raise forms.ValidationError(
                "Informe o telefone com DDD (10 ou 11 dígitos)."
            )
        return telefone

    def clean_rg(self):
        """Normaliza como o `save()` grava, para a unicidade bater.

        Também reconhece a marca de "não possui" escrita como se lê, com
        acento e til: sem isso ela viraria o RG literal "NÃOPOSSUIRG" —
        um documento inventado, e único, que derrubaria o segundo cadastro
        de quem não tem RG.
        """
        rg = (self.cleaned_data.get("rg") or "").strip()
        if not rg:
            return ""
        if normalizar_maiusculas(rg) in {RG_NAO_POSSUI, RG_NAO_POSSUI_EXIBICAO}:
            return RG_NAO_POSSUI
        return normalizar_rg(rg)


class ViaturaForm(forms.ModelForm):
    # Mesma razão do CPF: a placa é guardada sem hífen (7 caracteres), mas
    # "ABC-1234" tem 8 e é como as pessoas escrevem.
    placa = forms.CharField(label="placa", max_length=10)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instancia = self.instance if self.instance and self.instance.pk else None
        apenas_ativos(self.fields["combustivel"], instancia and instancia.combustivel_id)
        apenas_ativos(self.fields["unidade"], instancia and instancia.unidade_id)
        # Motoristas é M2M: o vínculo existente é preservado pelo próprio
        # queryset dos já selecionados.
        campo = self.fields["motoristas"]
        vinculados = (
            list(instancia.motoristas.values_list("pk", flat=True)) if instancia else []
        )
        campo.queryset = (
            campo.queryset.filter(ativo=True) | campo.queryset.filter(pk__in=vinculados)
        ).distinct()

    class Meta:
        model = Viatura
        fields = [
            "placa",
            "modelo",
            "tipo",
            "combustivel",
            "unidade",
            "motoristas",
            "ativo",
        ]
        help_texts = {"placa": "Formato antigo (ABC1234) ou Mercosul (ABC1D23)."}

    def clean_placa(self):
        placa = normalizar_placa(self.cleaned_data.get("placa"))
        if not placa:
            raise forms.ValidationError("Informe a placa.")
        if not placa_valida(placa):
            raise forms.ValidationError(
                "Placa inválida. Use o formato ABC1234 ou ABC1D23."
            )
        return placa


class TabelaDiariaForm(forms.ModelForm):
    """Só o valor de 24 h é digitado; 15% e 30% saem dele no ``save`` do modelo."""

    class Meta:
        model = TabelaDiaria
        fields = ["faixa", "vigencia_inicio", "valor_24h"]
        widgets = {"vigencia_inicio": forms.DateInput(attrs={"type": "date"})}

    def clean_valor_24h(self):
        valor = self.cleaned_data.get("valor_24h")
        if valor is None:
            return valor
        if valor <= 0:
            raise forms.ValidationError("O valor da diária deve ser maior que zero.")
        # Abaixo de R$ 0,04 o percentual de 15% arredonda para zero e o banco
        # recusa a gravação (os derivados também são defendidos por constraint).
        # Barrar aqui devolve erro de campo em vez de erro 500.
        quinze, _ = TabelaDiaria.derivar(valor)
        if quinze <= 0:
            raise forms.ValidationError(
                "Valor muito baixo: o percentual de 15% ficaria zerado."
            )
        return valor
