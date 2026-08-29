"""Formulários das solicitações de evento social.

A renderização é feita manualmente pelos components aprovados do design
system; estes formulários concentram validação e persistência.
"""

from django import forms
from django.db import transaction

from cadastros.models import Equipe, Motorista, Municipio, OrgaoResponsavel, Servico, TipoEvento

from .models import (
    DecisaoDG,
    SolicitacaoEvento,
    SolicitacaoEventoEquipe,
    SolicitacaoEventoServico,
    StatusSolicitacao,
)
from .services import CAMPOS_OBRIGATORIOS_ENVIO


def _queryset_ativo(model, instance_pk=None):
    """Registros ativos + o registro já vinculado (histórico continua legível)."""
    qs = model.objects.filter(ativo=True)
    if instance_pk:
        qs = qs | model.objects.filter(pk=instance_pk)
    return qs.distinct()


def _sincronizar_vinculos(manager, campo_fk, selecionados):
    """Sincroniza os modelos-through sem duplicar nem perder observações."""
    atuais = {getattr(item, f"{campo_fk}_id"): item for item in manager.all()}
    desejados = {obj.pk for obj in selecionados}
    for pk, item in atuais.items():
        if pk not in desejados:
            item.delete()
    novos = [
        manager.model(
            **{"solicitacao": manager.instance, campo_fk: obj}
        )
        for obj in selecionados
        if obj.pk not in atuais
    ]
    manager.model.objects.bulk_create(novos)


class SolicitacaoForm(forms.ModelForm):
    servicos = forms.ModelMultipleChoiceField(
        queryset=Servico.objects.none(), required=False, label="Serviços solicitados"
    )
    equipes = forms.ModelMultipleChoiceField(
        queryset=Equipe.objects.none(), required=False, label="Equipes"
    )
    unidade_movel = forms.BooleanField(required=False, label="Unidade móvel")
    veiculo_exposicao = forms.BooleanField(required=False, label="Veículos de exposição")

    class Meta:
        model = SolicitacaoEvento
        fields = [
            "data_solicitacao",
            "data_inicio_evento",
            "data_fim_evento",
            "tipo_evento",
            "municipio",
            "local_evento",
            "solicitante_nome",
            "solicitante_cargo",
            "solicitante_unidade",
            "contato",
            "orgao_responsavel",
            "unidade_movel",
            "veiculo_exposicao",
            "descricao_complementar",
            "quantidade_servidores",
            "tipo_operacao",
            "quantidade_cin",
            "motorista",
        ]

    def __init__(self, *args, enviar=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.enviar = enviar
        instancia = self.instance if self.instance.pk else None
        self.fields["tipo_evento"].queryset = _queryset_ativo(
            TipoEvento, instancia and instancia.tipo_evento_id
        )
        self.fields["municipio"].queryset = _queryset_ativo(
            Municipio, instancia and instancia.municipio_id
        ).select_related("regiao")
        self.fields["orgao_responsavel"].queryset = _queryset_ativo(
            OrgaoResponsavel, instancia and instancia.orgao_responsavel_id
        )
        self.fields["motorista"].queryset = _queryset_ativo(
            Motorista, instancia and instancia.motorista_id
        )
        self.fields["servicos"].queryset = (
            Servico.objects.filter(ativo=True)
            | (instancia.servicos.all() if instancia else Servico.objects.none())
        ).distinct()
        self.fields["equipes"].queryset = (
            Equipe.objects.filter(ativo=True)
            | (instancia.equipes.all() if instancia else Equipe.objects.none())
        ).distinct()
        if instancia:
            self.initial.setdefault("servicos", list(instancia.servicos.all()))
            self.initial.setdefault("equipes", list(instancia.equipes.all()))

    def clean(self):
        dados = super().clean()
        inicio = dados.get("data_inicio_evento")
        fim = dados.get("data_fim_evento")
        if inicio and fim and fim < inicio:
            self.add_error(
                "data_fim_evento", "A data de fim não pode ser anterior à data de início."
            )
        if self.enviar:
            for campo in CAMPOS_OBRIGATORIOS_ENVIO:
                if campo in self.fields and not dados.get(campo):
                    self.add_error(campo, "Campo obrigatório para o envio.")
            if not dados.get("servicos"):
                self.add_error(
                    "servicos", "Selecione ao menos um serviço para enviar a solicitação."
                )
        return dados

    @transaction.atomic
    def save(self, criado_por=None):
        solicitacao = super().save(commit=False)
        if not solicitacao.pk:
            solicitacao.criado_por = criado_por
        solicitacao.save()
        _sincronizar_vinculos(
            solicitacao.itens_servico, "servico", self.cleaned_data.get("servicos") or []
        )
        _sincronizar_vinculos(
            solicitacao.itens_equipe, "equipe", self.cleaned_data.get("equipes") or []
        )
        return solicitacao


class PlanejamentoForm(forms.ModelForm):
    """Edição restrita ao planejamento operacional (perfil analista)."""

    equipes = forms.ModelMultipleChoiceField(
        queryset=Equipe.objects.none(), required=False, label="Equipes"
    )
    unidade_movel = forms.BooleanField(required=False, label="Unidade móvel")
    veiculo_exposicao = forms.BooleanField(required=False, label="Veículos de exposição")

    class Meta:
        model = SolicitacaoEvento
        fields = [
            "unidade_movel",
            "veiculo_exposicao",
            "descricao_complementar",
            "quantidade_servidores",
            "tipo_operacao",
            "quantidade_cin",
            "motorista",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instancia = self.instance if self.instance.pk else None
        self.fields["motorista"].queryset = _queryset_ativo(
            Motorista, instancia and instancia.motorista_id
        )
        self.fields["equipes"].queryset = (
            Equipe.objects.filter(ativo=True)
            | (instancia.equipes.all() if instancia else Equipe.objects.none())
        ).distinct()
        if instancia:
            self.initial.setdefault("equipes", list(instancia.equipes.all()))

    @transaction.atomic
    def save(self, criado_por=None):
        solicitacao = super().save()
        _sincronizar_vinculos(
            solicitacao.itens_equipe, "equipe", self.cleaned_data.get("equipes") or []
        )
        return solicitacao


class DespachoForm(forms.Form):
    decisao = forms.ChoiceField(
        label="Decisão",
        choices=[
            (DecisaoDG.ATENDER, "Atender"),
            (DecisaoDG.NAO_ATENDER, "Não atender"),
            (DecisaoDG.CANCELADO, "Evento cancelado"),
        ],
        error_messages={"required": "Selecione a decisão da DG."},
    )
    observacao = forms.CharField(label="Observações DG", required=False)

    def clean(self):
        dados = super().clean()
        decisao = dados.get("decisao")
        observacao = (dados.get("observacao") or "").strip()
        if decisao in {DecisaoDG.NAO_ATENDER, DecisaoDG.CANCELADO} and not observacao:
            self.add_error(
                "observacao",
                "A observação é obrigatória para não atendimento ou cancelamento.",
            )
        dados["observacao"] = observacao
        return dados


class FiltroSolicitacoesForm(forms.Form):
    """Filtros da listagem (GET)."""

    q = forms.CharField(required=False, label="Busca")
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[("", "Todos os status")] + list(StatusSolicitacao.choices),
    )
    municipio = forms.ModelChoiceField(
        required=False, label="Município", queryset=Municipio.objects.all()
    )
    tipo_evento = forms.ModelChoiceField(
        required=False, label="Tipo do evento", queryset=TipoEvento.objects.all()
    )
    inicio = forms.DateField(required=False, label="Eventos a partir de")
    fim = forms.DateField(required=False, label="Eventos até")
