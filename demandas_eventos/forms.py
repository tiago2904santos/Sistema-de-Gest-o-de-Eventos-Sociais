from django import forms
from django.db import transaction
from django.utils import timezone

from cadastros.models import Municipio

from .models import DemandaEvento, Palestrante, RespostaPadrao, Tema
from .permissions import setores_do_usuario_para_modulo


class DemandaEventoForm(forms.ModelForm):
    """O formulário de palestras: um campo por coluna da planilha.

    A ordem dos campos é a das colunas da aba 2026, com Tema e Servidor (das
    abas anteriores) junto do evento. Os setores não aparecem: a linha
    pertence aos setores de quem a registra, como antes.
    """

    versao = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = DemandaEvento
        fields = [
            "municipio",
            "data_inicio_evento",
            "data_fim_evento",
            "periodo_evento_texto",
            "evento",
            "status",
            "andamento",
            "informacoes_previas",
            "solicitante",
            "contato",
            "data_solicitacao",
            "canal_solicitacao",
            "descricao",
            "quantidade_publico",
            "assunto_email",
            "pedido_contato",
            "tema",
            "servidor",
        ]
        widgets = {
            "andamento": forms.Textarea,
            "informacoes_previas": forms.Textarea,
            "descricao": forms.Textarea,
            "pedido_contato": forms.Textarea,
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.fields["municipio"].queryset = Municipio.objects.filter(ativo=True).select_related("estado")
        self.fields["tema"].queryset = Tema.objects.all()
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("data_solicitacao", timezone.localdate())
        if self.instance.pk:
            self.initial["versao"] = str(
                int(self.instance.atualizado_em.timestamp() * 1_000_000)
            )

    def clean(self):
        dados = super().clean()
        inicio = dados.get("data_inicio_evento")
        fim = dados.get("data_fim_evento")
        if fim and not inicio:
            self.add_error("data_fim_evento", "Informe a data inicial do evento.")
        if inicio and fim and fim < inicio:
            self.add_error("data_fim_evento", "A data final não pode ser anterior à inicial.")
        if self.instance.pk:
            atual = type(self.instance).objects.filter(pk=self.instance.pk).values_list(
                "atualizado_em", flat=True
            ).first()
            if atual and dados.get("versao") != str(
                int(atual.timestamp() * 1_000_000)
            ):
                raise forms.ValidationError(
                    "Este registro foi alterado por outra pessoa. Recarregue a página antes de salvar."
                )
        return dados

    @transaction.atomic
    def save(self, criado_por=None):
        demanda = super().save(commit=False)
        novo = not demanda.pk
        if novo:
            demanda.criado_por = criado_por
        if demanda.municipio_id:
            # O texto original só serve enquanto o município não foi escolhido.
            demanda.municipio_texto = ""
        demanda.full_clean(exclude=["setores"])
        demanda.save()
        if novo:
            demanda.setores.set(setores_do_usuario_para_modulo(self.usuario))
        return demanda


class TemaForm(forms.ModelForm):
    class Meta:
        model = Tema
        fields = ["nome"]


class PalestranteForm(forms.ModelForm):
    class Meta:
        model = Palestrante
        fields = ["municipio", "divisao", "lotacao", "nome", "contato", "email", "tema_abordagem"]


class RespostaPadraoForm(forms.ModelForm):
    class Meta:
        model = RespostaPadrao
        fields = ["tipo", "mensagem"]
        widgets = {"mensagem": forms.Textarea}
