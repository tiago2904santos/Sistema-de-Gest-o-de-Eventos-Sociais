"""Formulários das solicitações de evento social.

A renderização é feita manualmente pelos components aprovados do design
system; estes formulários concentram validação e persistência.
"""

from django import forms
from django.db import transaction

from cadastros.models import (
    Equipe,
    Estado,
    Motorista,
    Municipio,
    OrgaoResponsavel,
    Servico,
    TipoEvento,
    UnidadeMovel,
)

from .models import (
    DecisaoDG,
    SolicitacaoEvento,
    SolicitacaoEventoEquipe,
    SolicitacaoEventoServico,
    StatusSolicitacao,
    TipoOperacao,
)
from .services import CAMPOS_OBRIGATORIOS_ENVIO


def _campo_sim_nao(rotulo):
    """Campo booleano para os controles segmentados Sim/Não (valores "1"/"0").

    forms.BooleanField com CheckboxInput interpretaria "0" como True.
    """
    return forms.TypedChoiceField(
        label=rotulo,
        choices=[("1", "Sim"), ("0", "Não")],
        coerce=lambda valor: valor == "1",
        required=False,
        empty_value=False,
    )


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


def _ler_quantidades_equipes(form, equipes):
    """Lê a quantidade informada ao lado de cada equipe selecionada."""
    quantidades = {}
    for equipe in equipes:
        valor = str(form.data.get(f"quantidade_equipe_{equipe.pk}", "")).strip()
        if not valor:
            quantidades[equipe.pk] = None
            continue
        try:
            quantidade = int(valor)
        except (TypeError, ValueError):
            quantidade = 0
        if quantidade < 1:
            form.add_error(
                "equipes",
                f"Informe uma quantidade válida de servidores para {equipe}.",
            )
            quantidades[equipe.pk] = None
        else:
            quantidades[equipe.pk] = quantidade
    return quantidades


def _sincronizar_equipes(solicitacao, selecionadas, quantidades):
    """Sincroniza as equipes e recalcula o total a partir de suas quantidades."""
    atuais = {item.equipe_id: item for item in solicitacao.itens_equipe.all()}
    desejadas = {equipe.pk for equipe in selecionadas}

    for equipe_id, item in atuais.items():
        if equipe_id not in desejadas:
            item.delete()

    for equipe in selecionadas:
        quantidade = quantidades.get(equipe.pk)
        item = atuais.get(equipe.pk)
        if item:
            if item.quantidade_servidores != quantidade:
                item.quantidade_servidores = quantidade
                item.save(update_fields=["quantidade_servidores"])
        else:
            SolicitacaoEventoEquipe.objects.create(
                solicitacao=solicitacao,
                equipe=equipe,
                quantidade_servidores=quantidade,
            )

    solicitacao.recalcular_quantidade_servidores()


class SolicitacaoForm(forms.ModelForm):
    """Formulário único da solicitação: dados, serviços e planejamento.

    Quem cria também revisa e envia — não existe etapa de análise separada.
    """

    estado = forms.ModelChoiceField(
        queryset=Estado.objects.none(), required=False, label="Estado"
    )
    servicos = forms.ModelMultipleChoiceField(
        queryset=Servico.objects.none(), required=False, label="Serviços solicitados"
    )
    equipes = forms.ModelMultipleChoiceField(
        queryset=Equipe.objects.none(), required=False, label="Equipes"
    )
    unidade_movel = _campo_sim_nao("Unidade móvel")
    veiculo_exposicao = _campo_sim_nao("Veículos de exposição")

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
            "solicitante_cargo_unidade",
            "contato",
            "orgao_responsavel",
            "unidade_movel",
            "unidade_movel_designada",
            "veiculo_exposicao",
            "descricao_complementar",
            "tipo_operacao",
            "quantidade_cin",
            "motorista",
        ]

    def __init__(self, *args, enviar=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.enviar = enviar
        instancia = self.instance if self.instance.pk else None
        self.fields["estado"].queryset = _queryset_ativo(
            Estado,
            instancia and instancia.municipio and instancia.municipio.estado_id,
        )
        self.fields["tipo_evento"].queryset = _queryset_ativo(
            TipoEvento, instancia and instancia.tipo_evento_id
        )
        self.fields["municipio"].queryset = _queryset_ativo(
            Municipio, instancia and instancia.municipio_id
        ).select_related("estado", "regiao")
        self.fields["orgao_responsavel"].queryset = _queryset_ativo(
            OrgaoResponsavel, instancia and instancia.orgao_responsavel_id
        )
        self.fields["motorista"].queryset = _queryset_ativo(
            Motorista, instancia and instancia.motorista_id
        )
        self.fields["unidade_movel_designada"].queryset = _queryset_ativo(
            UnidadeMovel, instancia and instancia.unidade_movel_designada_id
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
            if instancia.municipio_id:
                self.initial.setdefault("estado", instancia.municipio.estado_id)
            self.initial.setdefault("servicos", list(instancia.servicos.all()))
            self.initial.setdefault("equipes", list(instancia.equipes.all()))
        elif not self.is_bound:
            parana = self.fields["estado"].queryset.filter(sigla="PR").first()
            if parana:
                self.initial.setdefault("estado", parana.pk)

    def clean(self):
        dados = super().clean()
        dados["tipo_operacao"] = dados.get("tipo_operacao") or TipoOperacao.DIARIA
        tipo_evento = dados.get("tipo_evento")
        estado = dados.get("estado")
        municipio = dados.get("municipio")
        if estado and municipio and municipio.estado_id != estado.pk:
            self.add_error(
                "municipio", "Selecione um município pertencente ao estado informado."
            )
        if tipo_evento and tipo_evento.nome.casefold() == "paraná em ação".casefold():
            dados["solicitante_nome"] = "Paraná em Ação"
            dados["solicitante_cargo_unidade"] = "SEJU"
        inicio = dados.get("data_inicio_evento")
        fim = dados.get("data_fim_evento")
        if inicio and fim and fim < inicio:
            self.add_error(
                "data_fim_evento", "A data de fim não pode ser anterior à data de início."
            )
        if self.enviar:
            if not estado:
                self.add_error("estado", "Campo obrigatório para o envio.")
            for campo in CAMPOS_OBRIGATORIOS_ENVIO:
                if campo in self.fields and not dados.get(campo):
                    self.add_error(campo, "Campo obrigatório para o envio.")
            if not dados.get("servicos"):
                self.add_error(
                    "servicos", "Selecione ao menos um serviço para enviar a solicitação."
                )
            if not dados.get("equipes"):
                self.add_error(
                    "equipes", "Designe ao menos uma equipe para enviar à DG."
                )
        # Motorista e a unidade designada só se aplicam com unidade móvel.
        if not dados.get("unidade_movel"):
            dados["motorista"] = None
            dados["unidade_movel_designada"] = None
        elif self.enviar and not dados.get("unidade_movel_designada"):
            self.add_error(
                "unidade_movel_designada",
                "Informe qual unidade móvel vai ao evento.",
            )
        self.quantidades_equipes = _ler_quantidades_equipes(
            self, dados.get("equipes") or []
        )
        if self.enviar:
            for equipe in dados.get("equipes") or []:
                if not self.quantidades_equipes.get(equipe.pk):
                    self.add_error(
                        "equipes",
                        f"Informe a quantidade de servidores de {equipe} para enviar à DG.",
                    )
                    break
        return dados

    def clean_motorista(self):
        motorista = self.cleaned_data.get("motorista")
        return motorista if self.cleaned_data.get("unidade_movel") else None

    def clean_unidade_movel_designada(self):
        designada = self.cleaned_data.get("unidade_movel_designada")
        return designada if self.cleaned_data.get("unidade_movel") else None

    @transaction.atomic
    def save(self, criado_por=None):
        solicitacao = super().save(commit=False)
        if not solicitacao.pk:
            solicitacao.criado_por = criado_por
        solicitacao.save()
        _sincronizar_vinculos(
            solicitacao.itens_servico, "servico", self.cleaned_data.get("servicos") or []
        )
        _sincronizar_equipes(
            solicitacao,
            self.cleaned_data.get("equipes") or [],
            self.quantidades_equipes,
        )
        return solicitacao


class AnexoForm(forms.Form):
    """Upload de anexo: tipos de documento comuns, até 10 MB."""

    EXTENSOES_PERMITIDAS = {
        "pdf", "png", "jpg", "jpeg", "doc", "docx", "xls", "xlsx", "odt", "ods",
    }
    TAMANHO_MAXIMO = 10 * 1024 * 1024

    arquivo = forms.FileField(
        label="Arquivo",
        error_messages={"required": "Selecione um arquivo para anexar."},
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        extensao = arquivo.name.rsplit(".", 1)[-1].lower() if "." in arquivo.name else ""
        if extensao not in self.EXTENSOES_PERMITIDAS:
            raise forms.ValidationError(
                "Tipo de arquivo não permitido. Use: "
                + ", ".join(sorted(self.EXTENSOES_PERMITIDAS)) + "."
            )
        if arquivo.size > self.TAMANHO_MAXIMO:
            raise forms.ValidationError("O arquivo não pode passar de 10 MB.")
        return arquivo


class DespachoForm(forms.Form):
    # Além das decisões finais, a DG pode devolver para o criador ajustar.
    DEVOLVER = "DEVOLVER"

    decisao = forms.ChoiceField(
        label="Decisão",
        choices=[
            (DecisaoDG.ATENDER, "Atender"),
            (DecisaoDG.NAO_ATENDER, "Não atender"),
            (DecisaoDG.CANCELADO, "Evento cancelado"),
            (DEVOLVER, "Devolver para ajuste"),
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
        if decisao == self.DEVOLVER and not observacao:
            self.add_error(
                "observacao",
                "Informe o motivo da devolução para o solicitante ajustar.",
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Só municípios que já têm solicitações: filtro útil e página leve.
        self.fields["municipio"].queryset = (
            Municipio.objects.filter(solicitacoes__isnull=False)
            .distinct()
            .order_by("nome")
        )
