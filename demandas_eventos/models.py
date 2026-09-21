from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class StatusDemanda(models.TextChoices):
    """A coluna "Status da demanda" da planilha."""

    PENDENTE = "PENDENTE", "Pendente"
    EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
    AGUARDANDO_RETORNO = "AGUARDANDO_RETORNO", "Aguardando retorno"
    EVENTO_AGENDADO = "EVENTO_AGENDADO", "Agendada"
    ATENDIDA = "ATENDIDA", "Atendida"
    CANCELADA = "CANCELADA", "Cancelada"


class TipoEventoPalestra(models.TextChoices):
    """A coluna "Evento" da planilha: os três tipos que a ASCOM atende."""

    PALESTRA = "PALESTRA", "Palestra"
    PCPR_NA_COMUNIDADE = "PCPR_NA_COMUNIDADE", "PCPR na Comunidade"
    EVENTO = "EVENTO", "Evento"


class Tema(models.Model):
    """A aba TEMAS da planilha — só os temas dela, nada além."""

    nome = models.CharField("nome", max_length=200, unique=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "tema"
        verbose_name_plural = "temas"

    def __str__(self):
        return self.nome


class Palestrante(models.Model):
    """A aba PALESTRANTES da planilha."""

    nome = models.CharField("servidor", max_length=200)
    municipio = models.ForeignKey(
        "cadastros.Municipio",
        verbose_name="município",
        on_delete=models.PROTECT,
        related_name="palestrantes_ascom",
        blank=True,
        null=True,
    )
    municipio_texto = models.CharField("município (texto original)", max_length=150, blank=True)
    divisao = models.CharField("divisão", max_length=100, blank=True)
    lotacao = models.CharField("lotação", max_length=150, blank=True)
    contato = models.CharField("contato", max_length=100, blank=True)
    email = models.EmailField("e-mail", blank=True)
    tema_abordagem = models.CharField("tema de abordagem", max_length=300, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "palestrante"
        verbose_name_plural = "palestrantes"
        constraints = [
            models.UniqueConstraint(
                fields=["nome", "lotacao"], name="palestrante_unico_por_nome_lotacao"
            )
        ]

    def __str__(self):
        return self.nome


class RespostaPadrao(models.Model):
    """A aba "Respostas Padrão" da planilha."""

    tipo = models.CharField("tipo", max_length=200, unique=True)
    mensagem = models.TextField("mensagem")
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["tipo"]
        verbose_name = "resposta padrão"
        verbose_name_plural = "respostas padrão"

    def __str__(self):
        return self.tipo


class DemandaEvento(models.Model):
    """Uma linha da planilha "Palestras e Eventos ASCOM".

    Cada campo é uma coluna da aba do ano (2026): Município, Data do evento e
    hora (período), Evento, Status da demanda, Andamento, Informações prévias,
    Solicitante, Contato, Data da solicitação, Foi solicitado via, Descrição,
    Quantidade de público, Assunto e-mail e Pedido/Contato — mais Tema e
    Servidor, das abas dos anos anteriores. O "Mês" da planilha não é campo:
    sai da data do evento (ou da solicitação, quando o evento não tem data).
    """

    municipio = models.ForeignKey(
        "cadastros.Municipio",
        verbose_name="município",
        on_delete=models.PROTECT,
        related_name="demandas_ascom",
        blank=True,
        null=True,
    )
    municipio_texto = models.CharField("município (texto original)", max_length=150, blank=True)
    data_inicio_evento = models.DateField("data do evento", blank=True, null=True)
    data_fim_evento = models.DateField("fim do evento", blank=True, null=True)
    periodo_evento_texto = models.CharField("hora (período)", max_length=200, blank=True)
    evento = models.CharField(
        "evento",
        max_length=25,
        choices=TipoEventoPalestra.choices,
        default=TipoEventoPalestra.PALESTRA,
    )
    status = models.CharField(
        "status da demanda",
        max_length=25,
        choices=StatusDemanda.choices,
        default=StatusDemanda.PENDENTE,
    )
    andamento = models.TextField("andamento", blank=True)
    informacoes_previas = models.TextField("informações prévias", blank=True)
    solicitante = models.CharField("solicitante", max_length=1000)
    contato = models.CharField("contato", max_length=300, blank=True)
    data_solicitacao = models.DateField("data da solicitação")
    canal_solicitacao = models.CharField("foi solicitado via", max_length=150, blank=True)
    descricao = models.TextField("descrição", blank=True)
    quantidade_publico = models.PositiveIntegerField("quantidade de público", blank=True, null=True)
    assunto_email = models.CharField("assunto e-mail", max_length=300, blank=True)
    pedido_contato = models.TextField("pedido/contato", blank=True)
    tema = models.ForeignKey(
        Tema,
        verbose_name="tema",
        on_delete=models.PROTECT,
        related_name="demandas",
        blank=True,
        null=True,
    )
    servidor = models.CharField("servidor", max_length=300, blank=True)
    # Daqui para baixo nada é coluna da planilha: dizem quem enxerga a linha
    # (o setor de quem a registrou) e de onde ela veio.
    setores = models.ManyToManyField(
        "accounts.Setor", verbose_name="setores envolvidos", related_name="demandas_eventos"
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criado por",
        on_delete=models.PROTECT,
        related_name="demandas_ascom_criadas",
        blank=True,
        null=True,
    )
    origem_importacao = models.CharField("origem da importação", max_length=100, blank=True)
    chave_importacao = models.CharField(
        "chave da importação", max_length=64, unique=True, blank=True, null=True
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["-data_solicitacao", "-pk"]
        verbose_name = "palestra ou evento"
        verbose_name_plural = "palestras e eventos"
        indexes = [
            models.Index(fields=["status", "data_solicitacao"], name="demanda_status_data_idx"),
            models.Index(fields=["data_inicio_evento"], name="demanda_evento_data_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(data_inicio_evento__isnull=True)
                    | models.Q(data_fim_evento__isnull=True)
                    | models.Q(data_fim_evento__gte=models.F("data_inicio_evento"))
                ),
                name="demanda_periodo_evento_valido",
            )
        ]

    def __str__(self):
        return f"{self.get_evento_display()} #{self.pk}"

    def clean(self):
        super().clean()
        if (
            self.data_inicio_evento
            and self.data_fim_evento
            and self.data_fim_evento < self.data_inicio_evento
        ):
            raise ValidationError({"data_fim_evento": "A data final não pode ser anterior à inicial."})

    @property
    def finalizada(self):
        return self.status in {StatusDemanda.ATENDIDA, StatusDemanda.CANCELADA}

    @property
    def mes_referencia(self):
        """O "Mês" da planilha: o do evento, senão o da solicitação."""
        return self.data_inicio_evento or self.data_solicitacao

    @property
    def municipio_display(self):
        return str(self.municipio) if self.municipio_id else self.municipio_texto

    @property
    def data_evento_display(self):
        inicio, fim = self.data_inicio_evento, self.data_fim_evento
        if inicio and fim and fim != inicio:
            return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"
        return f"{inicio:%d/%m/%Y}" if inicio else ""

    @property
    def periodo_evento_display(self):
        """A coluna "Data do evento e hora (período)" como a planilha a lê."""
        return " · ".join(
            parte for parte in (self.data_evento_display, self.periodo_evento_texto) if parte
        )


class AcaoHistoricoDemanda(models.TextChoices):
    CRIACAO = "CRIACAO", "Registro criado"
    ATUALIZACAO = "ATUALIZACAO", "Registro atualizado"
    TRANSICAO = "TRANSICAO", "Status alterado"


class HistoricoDemanda(models.Model):
    demanda = models.ForeignKey(
        DemandaEvento,
        on_delete=models.CASCADE,
        related_name="historico",
        verbose_name="demanda",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="historico_demandas_ascom",
        null=True,
        blank=True,
        verbose_name="usuário",
    )
    acao = models.CharField(
        "ação", max_length=20, choices=AcaoHistoricoDemanda.choices
    )
    status_anterior = models.CharField("status anterior", max_length=25, blank=True)
    status_novo = models.CharField("status novo", max_length=25, blank=True)
    descricao = models.TextField("descrição", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        ordering = ["criado_em", "pk"]
        verbose_name = "histórico de palestra ou evento"
        verbose_name_plural = "históricos de palestras e eventos"

    def __str__(self):
        return f"{self.demanda_id} — {self.get_acao_display()}"

    @property
    def status_novo_display(self):
        return dict(StatusDemanda.choices).get(self.status_novo, self.status_novo)
