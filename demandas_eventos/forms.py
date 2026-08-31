from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction

from cadastros.models import Municipio, TipoEvento

from .models import DemandaEvento, Palestrante, RespostaPadrao, Tema
from .permissions import setores_do_usuario_para_modulo


class DemandaEventoForm(forms.ModelForm):
    class Meta:
        model = DemandaEvento
        fields = [
            "data_solicitacao",
            "tipo_evento",
            "tema",
            "canal_solicitacao",
            "municipio",
            "data_inicio_evento",
            "data_fim_evento",
            "periodo_evento_texto",
            "solicitante",
            "contato",
            "assunto_email",
            "pedido_contato",
            "descricao",
            "status",
            "andamento",
            "informacoes_previas",
            "responsavel_organizacao",
            "responsavel_atendimento",
            "palestrantes",
            "unidade",
            "quantidade_publico",
            "briefing",
            "materia_site",
            "setores",
        ]
        widgets = {
            "pedido_contato": forms.Textarea,
            "descricao": forms.Textarea,
            "andamento": forms.Textarea,
            "informacoes_previas": forms.Textarea,
            "briefing": forms.Textarea,
            "materia_site": forms.Textarea,
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.fields["tipo_evento"].queryset = TipoEvento.objects.filter(ativo=True)
        self.fields["tema"].queryset = Tema.objects.filter(ativo=True)
        self.fields["municipio"].queryset = Municipio.objects.filter(ativo=True).select_related("estado")
        self.fields["palestrantes"].queryset = Palestrante.objects.filter(ativo=True)
        self.fields["responsavel_atendimento"].queryset = get_user_model().objects.filter(is_active=True)
        self.fields["setores"].queryset = setores_do_usuario_para_modulo(usuario)
        if not self.is_bound and not self.instance.pk:
            self.initial["setores"] = list(self.fields["setores"].queryset)

    def clean(self):
        dados = super().clean()
        inicio = dados.get("data_inicio_evento")
        fim = dados.get("data_fim_evento")
        if inicio and fim and fim < inicio:
            self.add_error("data_fim_evento", "A data final não pode ser anterior à inicial.")
        if not dados.get("setores"):
            self.add_error("setores", "Selecione ao menos um setor envolvido.")
        return dados

    @transaction.atomic
    def save(self, criado_por=None):
        demanda = super().save(commit=False)
        if not demanda.pk:
            demanda.criado_por = criado_por
        demanda.full_clean(exclude=["setores"])
        demanda.save()
        self.save_m2m()
        return demanda


class TemaForm(forms.ModelForm):
    class Meta:
        model = Tema
        fields = ["nome", "ativo"]


class PalestranteForm(forms.ModelForm):
    class Meta:
        model = Palestrante
        fields = ["nome", "municipio", "divisao", "lotacao", "contato", "email", "temas", "ativo"]


class RespostaPadraoForm(forms.ModelForm):
    class Meta:
        model = RespostaPadrao
        fields = ["tipo", "mensagem", "ativo"]
        widgets = {"mensagem": forms.Textarea}
