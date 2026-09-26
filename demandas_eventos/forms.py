import re

from django import forms
from django.db import transaction
from django.utils import timezone

from cadastros.models import Estado, Municipio

from .models import CanalSolicitacao, DemandaEvento, Palestrante, RespostaPadrao, Tema
from .permissions import setores_do_usuario_para_modulo
from .planilha import formatar_telefone


class DemandaEventoForm(forms.ModelForm):
    """O formulário de palestras: um campo por coluna da planilha.

    A ordem dos campos é a das colunas da aba 2026, com Tema e Servidor (das
    abas anteriores) junto do evento. Os setores não aparecem: a linha
    pertence aos setores de quem a registra, como antes.
    """

    versao = forms.CharField(required=False, widget=forms.HiddenInput)
    # Não é coluna: é o primeiro passo do destino (estado → município), no
    # componente de destinos da Ordem de Serviço.
    estado = forms.ModelChoiceField(queryset=Estado.objects.order_by("sigla"), required=False, label="Estado")

    class Meta:
        model = DemandaEvento
        fields = [
            "municipio",
            "data_inicio_evento",
            "data_fim_evento",
            "hora_inicio",
            "evento",
            "informacoes_previas",
            "solicitante",
            "telefone",
            "email",
            "data_solicitacao",
            "canal_solicitacao",
            "protocolo",
            "descricao",
            "quantidade_publico",
            "assunto_email",
            "pedido_contato",
            "temas",
            "palestrantes",
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
        self.fields["temas"].queryset = Tema.objects.all()
        self.fields["palestrantes"].queryset = Palestrante.objects.select_related("municipio")
        if self.instance.municipio_id:
            self.initial.setdefault("estado", self.instance.municipio.estado_id)
        elif not self.is_bound:
            # Padrão pré-selecionado: quase tudo acontece no Paraná.
            parana = Estado.objects.filter(sigla="PR").values_list("pk", flat=True).first()
            if parana:
                self.initial.setdefault("estado", parana)
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("data_solicitacao", timezone.localdate())
        if self.instance.pk:
            self.initial["versao"] = str(
                int(self.instance.atualizado_em.timestamp() * 1_000_000)
            )

    def clean_telefone(self):
        digitos = re.sub(r"\D", "", self.cleaned_data.get("telefone") or "")
        if not digitos:
            return ""
        telefone = formatar_telefone(digitos)
        if not telefone:
            raise forms.ValidationError("Informe o telefone com DDD: (00) 0000-0000 ou (00) 00000-0000.")
        return telefone

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        dados = super().clean()
        inicio = dados.get("data_inicio_evento")
        fim = dados.get("data_fim_evento")
        if dados.get("canal_solicitacao") == CanalSolicitacao.PROTOCOLO:
            digitos = re.sub(r"\D", "", dados.get("protocolo") or "")
            if not digitos:
                self.add_error("protocolo", "Informe o número do protocolo.")
            elif len(digitos) != 9:
                self.add_error("protocolo", "O protocolo tem 9 dígitos (00.000.000-0).")
            else:
                dados["protocolo"] = f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}-{digitos[8]}"
        else:
            dados["protocolo"] = ""
        estado, municipio = dados.get("estado"), dados.get("municipio")
        if estado and municipio and municipio.estado_id != estado.pk:
            self.add_error("municipio", "O município não pertence ao estado escolhido.")
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
        if (demanda.telefone or demanda.email) and "contato" not in self.fields:
            # O contato escrito à mão foi trocado pelos campos de verdade.
            if self.initial.get("telefone") != demanda.telefone or self.initial.get("email") != demanda.email:
                demanda.contato = ""
        if demanda.hora_inicio:
            # O horário escrito à mão na planilha foi trocado pelo de verdade.
            demanda.periodo_evento_texto = ""
        if demanda.municipio_id:
            # O texto original só serve enquanto o município não foi escolhido.
            demanda.municipio_texto = ""
        demanda.full_clean(exclude=["setores", "temas", "palestrantes"])
        demanda.save()
        self.save_m2m()
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
        help_texts = {
            "mensagem": "No Responder da palestra, {solicitante}, {data}, {horario}, {municipio}, "
            "{palestrante} e {tema} viram os dados dela.",
        }
