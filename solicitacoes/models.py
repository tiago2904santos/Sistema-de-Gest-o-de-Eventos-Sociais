from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class StatusSolicitacao(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    ENVIADA = "ENVIADA", "Enviada"
    EM_ANALISE = "EM_ANALISE", "Em análise"
    AGUARDANDO_DESPACHO = "AGUARDANDO_DESPACHO", "Aguardando despacho"
    ATENDIDA = "ATENDIDA", "Atendida"
    NAO_ATENDIDA = "NAO_ATENDIDA", "Não atendida"
    CANCELADA = "CANCELADA", "Cancelada"


class DecisaoDG(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    ATENDER = "ATENDER", "Atender"
    NAO_ATENDER = "NAO_ATENDER", "Não atender"
    CANCELADO = "CANCELADO", "Evento cancelado"


class TipoOperacao(models.TextChoices):
    ORDINARIA = "ORDINARIA", "Ordinária"
    ITINERANTE = "ITINERANTE", "Itinerante"
    ESPECIAL = "ESPECIAL", "Especial"


class SolicitacaoEvento(models.Model):
    """Solicitação de evento social."""

    status = models.CharField(
        "status",
        max_length=25,
        choices=StatusSolicitacao.choices,
        default=StatusSolicitacao.RASCUNHO,
    )
    # Campos exigidos apenas no envio ficam opcionais no banco para permitir
    # rascunhos parciais; a obrigatoriedade é aplicada no formulário/serviço.
    data_solicitacao = models.DateField("data da solicitação", default=timezone.localdate)
    data_inicio_evento = models.DateField(
        "data de início do evento", blank=True, null=True
    )
    data_fim_evento = models.DateField("data de fim do evento", blank=True, null=True)

    municipio = models.ForeignKey(
        "cadastros.Municipio",
        verbose_name="município",
        on_delete=models.PROTECT,
        related_name="solicitacoes",
        blank=True,
        null=True,
    )
    regiao = models.ForeignKey(
        "cadastros.Regiao",
        verbose_name="região",
        on_delete=models.PROTECT,
        related_name="solicitacoes",
        blank=True,
        null=True,
        help_text="Preenchida automaticamente a partir do município.",
    )
    tipo_evento = models.ForeignKey(
        "cadastros.TipoEvento",
        verbose_name="tipo de evento",
        on_delete=models.PROTECT,
        related_name="solicitacoes",
        blank=True,
        null=True,
    )

    solicitante_nome = models.CharField("nome do solicitante", max_length=150, blank=True)
    solicitante_cargo = models.CharField("cargo do solicitante", max_length=100, blank=True)
    solicitante_unidade = models.CharField("unidade do solicitante", max_length=150, blank=True)
    contato = models.CharField("contato", max_length=100, blank=True)

    orgao_responsavel = models.ForeignKey(
        "cadastros.OrgaoResponsavel",
        verbose_name="órgão responsável",
        on_delete=models.PROTECT,
        related_name="solicitacoes",
        blank=True,
        null=True,
    )

    unidade_movel = models.BooleanField("unidade móvel", default=False)
    veiculo_exposicao = models.BooleanField("veículo de exposição", default=False)
    local_evento = models.CharField("local do evento", max_length=255, blank=True)
    descricao_complementar = models.TextField("descrição complementar", blank=True)

    quantidade_servidores = models.PositiveIntegerField(
        "quantidade de servidores", blank=True, null=True
    )
    tipo_operacao = models.CharField(
        "tipo de operação",
        max_length=20,
        choices=TipoOperacao.choices,
        blank=True,
    )
    quantidade_cin = models.PositiveIntegerField(
        "quantidade de CIN", blank=True, null=True
    )
    motorista = models.ForeignKey(
        "cadastros.Motorista",
        verbose_name="motorista",
        on_delete=models.PROTECT,
        related_name="solicitacoes",
        blank=True,
        null=True,
    )

    decisao_dg = models.CharField(
        "decisão da DG",
        max_length=15,
        choices=DecisaoDG.choices,
        default=DecisaoDG.PENDENTE,
    )
    observacoes_dg = models.TextField("observações da DG", blank=True)
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="decidido por",
        on_delete=models.PROTECT,
        related_name="solicitacoes_decididas",
        blank=True,
        null=True,
    )
    decidido_em = models.DateTimeField("decidido em", blank=True, null=True)

    servicos = models.ManyToManyField(
        "cadastros.Servico",
        verbose_name="serviços",
        through="SolicitacaoEventoServico",
        related_name="solicitacoes",
        blank=True,
    )
    equipes = models.ManyToManyField(
        "cadastros.Equipe",
        verbose_name="equipes",
        through="SolicitacaoEventoEquipe",
        related_name="solicitacoes",
        blank=True,
    )

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criado por",
        on_delete=models.PROTECT,
        related_name="solicitacoes_criadas",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "solicitação de evento"
        verbose_name_plural = "solicitações de evento"
        ordering = ["-data_solicitacao", "-criado_em"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(data_inicio_evento__isnull=True)
                    | models.Q(data_fim_evento__isnull=True)
                    | models.Q(data_fim_evento__gte=models.F("data_inicio_evento"))
                ),
                name="periodo_evento_valido",
            ),
        ]

    def __str__(self):
        return f"Solicitação #{self.pk} — {self.municipio} ({self.get_status_display()})"

    @property
    def mes_evento(self):
        """Mês do evento, derivado da data de início."""
        return self.data_inicio_evento.month if self.data_inicio_evento else None

    @property
    def finalizada(self):
        return self.status in {
            StatusSolicitacao.ATENDIDA,
            StatusSolicitacao.NAO_ATENDIDA,
            StatusSolicitacao.CANCELADA,
        }

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.data_inicio_evento
            and self.data_fim_evento
            and self.data_fim_evento < self.data_inicio_evento
        ):
            errors["data_fim_evento"] = "A data de fim não pode ser anterior à data de início."
        if (
            self.municipio_id
            and self.regiao_id
            and self.municipio.regiao_id != self.regiao_id
        ):
            errors["regiao"] = "A região deve corresponder à região do município selecionado."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Região sempre derivada do município.
        if self.municipio_id:
            self.regiao_id = self.municipio.regiao_id
        super().save(*args, **kwargs)


class SolicitacaoEventoServico(models.Model):
    solicitacao = models.ForeignKey(
        SolicitacaoEvento,
        verbose_name="solicitação",
        on_delete=models.CASCADE,
        related_name="itens_servico",
    )
    servico = models.ForeignKey(
        "cadastros.Servico",
        verbose_name="serviço",
        on_delete=models.PROTECT,
        related_name="itens_solicitacao",
    )
    observacao = models.CharField("observação", max_length=255, blank=True)

    class Meta:
        verbose_name = "serviço da solicitação"
        verbose_name_plural = "serviços da solicitação"
        constraints = [
            models.UniqueConstraint(
                fields=["solicitacao", "servico"], name="servico_unico_por_solicitacao"
            ),
        ]

    def __str__(self):
        return f"{self.solicitacao_id} — {self.servico}"


class SolicitacaoEventoEquipe(models.Model):
    solicitacao = models.ForeignKey(
        SolicitacaoEvento,
        verbose_name="solicitação",
        on_delete=models.CASCADE,
        related_name="itens_equipe",
    )
    equipe = models.ForeignKey(
        "cadastros.Equipe",
        verbose_name="equipe",
        on_delete=models.PROTECT,
        related_name="itens_solicitacao",
    )
    observacao = models.CharField("observação", max_length=255, blank=True)

    class Meta:
        verbose_name = "equipe da solicitação"
        verbose_name_plural = "equipes da solicitação"
        constraints = [
            models.UniqueConstraint(
                fields=["solicitacao", "equipe"], name="equipe_unica_por_solicitacao"
            ),
        ]

    def __str__(self):
        return f"{self.solicitacao_id} — {self.equipe}"


class AcaoHistorico(models.TextChoices):
    CRIACAO = "CRIACAO", "Rascunho criado"
    ATUALIZACAO = "ATUALIZACAO", "Solicitação atualizada"
    ENVIO = "ENVIO", "Solicitação enviada"
    INICIO_ANALISE = "INICIO_ANALISE", "Análise iniciada"
    PLANEJAMENTO = "PLANEJAMENTO", "Planejamento atualizado"
    ENCAMINHAMENTO_DESPACHO = "ENCAMINHAMENTO_DESPACHO", "Encaminhada para despacho"
    DECISAO = "DECISAO", "Decisão da DG registrada"


class HistoricoSolicitacao(models.Model):
    """Histórico persistente das ações relevantes de uma solicitação."""

    solicitacao = models.ForeignKey(
        SolicitacaoEvento,
        verbose_name="solicitação",
        on_delete=models.CASCADE,
        related_name="historico",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historico_solicitacoes",
    )
    acao = models.CharField("ação", max_length=30, choices=AcaoHistorico.choices)
    status_anterior = models.CharField(
        "status anterior", max_length=25, choices=StatusSolicitacao.choices, blank=True
    )
    status_novo = models.CharField(
        "status novo", max_length=25, choices=StatusSolicitacao.choices, blank=True
    )
    observacao = models.TextField("observação", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "histórico da solicitação"
        verbose_name_plural = "históricos da solicitação"
        ordering = ["criado_em", "pk"]

    def __str__(self):
        return f"{self.solicitacao_id} — {self.get_acao_display()}"
