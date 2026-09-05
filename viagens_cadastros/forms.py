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
    servidores = forms.ModelMultipleChoiceField(
        label="Servidores vinculados",
        queryset=Servidor.objects.none(),
        required=False,
        help_text=(
            "Selecione quem está lotado nesta unidade. Ao mover um servidor, "
            "a lotação anterior é atualizada automaticamente."
        ),
    )

    class Meta:
        model = Unidade
        fields = ["nome", "sigla"]
        widgets = {
            "nome": forms.TextInput(
                attrs={"placeholder": "Ex.: DELEGACIA DE CURITIBA", "data-uppercase": "true"}
            ),
            "sigla": forms.TextInput(
                attrs={"placeholder": "Ex.: DC", "data-uppercase": "true", "maxlength": "50"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["servidores"].queryset = Servidor.objects.select_related(
            "cargo", "unidade"
        ).order_by("nome")
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["servidores"] = list(
                Servidor.objects.filter(unidade=self.instance).values_list("pk", flat=True)
            )

    def save(self, commit=True):
        unidade = super().save(commit=commit)
        if commit:
            selecionados = self.cleaned_data.get("servidores")
            if selecionados is not None:
                ids = {servidor.pk for servidor in selecionados}
                Servidor.objects.filter(pk__in=ids).update(unidade=unidade)
                Servidor.objects.filter(unidade=unidade).exclude(pk__in=ids).update(
                    unidade=None
                )
        return unidade

    def clean_sigla(self):
        return normalizar_maiusculas(self.cleaned_data.get("sigla"))


class CargoForm(NomeNormalizadoMixin, forms.ModelForm):
    class Meta:
        model = Cargo
        fields = ["nome", "is_padrao"]
        labels = {"nome": "Cargo", "is_padrao": "Usar como cargo padrão"}
        help_texts = {
            "is_padrao": "Será sugerido automaticamente ao criar um servidor."
        }
        widgets = {
            "nome": forms.TextInput(
                attrs={"placeholder": "Ex.: INVESTIGADOR", "data-uppercase": "true"}
            )
        }


class CombustivelForm(NomeNormalizadoMixin, forms.ModelForm):
    class Meta:
        model = Combustivel
        fields = ["nome", "is_padrao"]
        labels = {"nome": "Combustível", "is_padrao": "Usar como combustível padrão"}
        help_texts = {
            "is_padrao": "Será sugerido automaticamente ao criar uma viatura."
        }
        widgets = {
            "nome": forms.TextInput(
                attrs={"placeholder": "Ex.: GASOLINA", "data-uppercase": "true"}
            )
        }


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
        widget=forms.TextInput(
            attrs={
                "placeholder": "000.000.000-00",
                "inputmode": "numeric",
                "autocomplete": "off",
                "data-mask": "cpf",
                "maxlength": "14",
            }
        ),
    )
    telefone = forms.CharField(
        label="Telefone",
        max_length=16,
        required=False,
        help_text="Com DDD. Pode digitar com ou sem pontuação.",
        widget=forms.TextInput(
            attrs={
                "placeholder": "(00) 00000-0000",
                "inputmode": "tel",
                "autocomplete": "tel",
                "data-mask": "telefone",
                "maxlength": "16",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cargo"].queryset = Cargo.objects.order_by("nome")
        self.fields["unidade"].queryset = Unidade.objects.order_by("nome")
        self.fields["cargo"].empty_label = "Selecione (opcional)"
        self.fields["unidade"].empty_label = "Selecione (opcional)"
        if not self.instance.pk and not self.is_bound:
            padrao = Cargo.objects.filter(is_padrao=True).first()
            if padrao:
                self.initial.setdefault("cargo", padrao.pk)

    class Meta:
        model = Servidor
        fields = ["nome", "cargo", "cpf", "rg", "telefone", "unidade"]
        help_texts = {
            "rg": f'Deixe em branco ou escreva "{RG_NAO_POSSUI_EXIBICAO}" se não possuir.',
        }
        widgets = {
            "nome": forms.TextInput(
                attrs={
                    "placeholder": "Ex.: MARIA DA SILVA",
                    "autocomplete": "name",
                    "data-uppercase": "true",
                }
            ),
            "rg": forms.TextInput(
                attrs={
                    "placeholder": "00.000.000-0 ou NÃO POSSUI RG",
                    "autocomplete": "off",
                    "data-mask": "rg",
                    "maxlength": "30",
                }
            ),
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
    placa = forms.CharField(
        label="Placa",
        max_length=10,
        widget=forms.TextInput(
            attrs={
                "placeholder": "ABC-1234 ou ABC1D23",
                "autocomplete": "off",
                "data-mask": "placa",
                "data-uppercase": "true",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["combustivel"].queryset = Combustivel.objects.order_by("nome")
        self.fields["unidade"].queryset = Unidade.objects.order_by("nome")
        self.fields["motoristas"].queryset = Servidor.objects.select_related(
            "cargo", "unidade"
        ).order_by("nome")
        self.fields["combustivel"].empty_label = "Selecione (opcional)"
        self.fields["unidade"].empty_label = "Selecione (opcional)"
        if not self.instance.pk and not self.is_bound:
            padrao = Combustivel.objects.filter(is_padrao=True).first()
            if padrao:
                self.initial.setdefault("combustivel", padrao.pk)
            self.initial.setdefault("tipo", Viatura.Tipo.DESCARACTERIZADA)

    class Meta:
        model = Viatura
        fields = [
            "placa",
            "modelo",
            "tipo",
            "combustivel",
            "unidade",
            "motoristas",
        ]
        help_texts = {
            "placa": "Formato antigo (ABC1234) ou Mercosul (ABC1D23).",
            "motoristas": "Selecione todos os servidores autorizados a conduzir esta viatura.",
        }
        widgets = {
            "modelo": forms.TextInput(
                attrs={"placeholder": "Ex.: RENAULT DUSTER", "data-uppercase": "true"}
            )
        }

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
        widgets = {
            "vigencia_inicio": forms.DateInput(attrs={"type": "date"}),
            "valor_24h": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0.04",
                    "inputmode": "decimal",
                    "placeholder": "0,00",
                    "data-diaria-base": "true",
                }
            ),
        }

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
