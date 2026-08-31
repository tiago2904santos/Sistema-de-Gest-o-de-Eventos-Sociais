from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class StatusDemanda(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    AGUARDANDO_RETORNO = "AGUARDANDO_RETORNO", "Aguardando retorno"
    EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
    EVENTO_AGENDADO = "EVENTO_AGENDADO", "Evento agendado"
    ATENDIDA = "ATENDIDA", "Atendida"
    NAO_ATENDER = "NAO_ATENDER", "Não atender"
    CANCELADA = "CANCELADA", "Cancelada"


class Tema(models.Model):
    nome = models.CharField("nome", max_length=200, unique=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "tema"
        verbose_name_plural = "temas"

    def __str__(self):
        return self.nome


class Palestrante(models.Model):
    nome = models.CharField("nome", max_length=200)
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
    temas = models.ManyToManyField(Tema, verbose_name="temas", related_name="palestrantes", blank=True)
    ativo = models.BooleanField("ativo", default=True)
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
    tipo = models.CharField("tipo", max_length=200, unique=True)
    mensagem = models.TextField("mensagem")
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["tipo"]
        verbose_name = "resposta padrão"
        verbose_name_plural = "respostas padrão"

    def __str__(self):
        return self.tipo


class DemandaEvento(models.Model):
    status = models.CharField(
        "status",
        max_length=25,
        choices=StatusDemanda.choices,
        default=StatusDemanda.PENDENTE,
    )
    data_solicitacao = models.DateField("data da solicitação")
    tipo_evento = models.ForeignKey(
        "cadastros.TipoEvento",
        verbose_name="tipo de evento",
        on_delete=models.PROTECT,
        related_name="demandas_ascom",
    )
    tema = models.ForeignKey(
        Tema,
        verbose_name="tema",
        on_delete=models.PROTECT,
        related_name="demandas",
        blank=True,
        null=True,
    )
    canal_solicitacao = models.CharField("solicitado via", max_length=150, blank=True)
    municipio = models.ForeignKey(
        "cadastros.Municipio",
        verbose_name="município",
        on_delete=models.PROTECT,
        related_name="demandas_ascom",
        blank=True,
        null=True,
    )
    municipio_texto = models.CharField("município (texto original)", max_length=150, blank=True)
    data_inicio_evento = models.DateField("início do evento", blank=True, null=True)
    data_fim_evento = models.DateField("fim do evento", blank=True, null=True)
    periodo_evento_texto = models.CharField("período do evento", max_length=200, blank=True)
    solicitante = models.CharField("solicitante", max_length=1000)
    contato = models.CharField("contato", max_length=300, blank=True)
    assunto_email = models.CharField("assunto do e-mail", max_length=300, blank=True)
    pedido_contato = models.TextField("pedido / contato", blank=True)
    descricao = models.TextField("descrição", blank=True)
    andamento = models.TextField("andamento", blank=True)
    informacoes_previas = models.TextField("informações prévias", blank=True)
    responsavel_organizacao = models.CharField("responsável pela organização", max_length=200, blank=True)
    responsavel_atendimento = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="responsável pelo atendimento",
        on_delete=models.SET_NULL,
        related_name="demandas_ascom_atribuidas",
        blank=True,
        null=True,
    )
    responsavel_atendimento_texto = models.CharField(
        "responsável pelo atendimento (texto original)", max_length=200, blank=True
    )
    palestrantes = models.ManyToManyField(
        Palestrante, verbose_name="palestrantes", related_name="demandas", blank=True
    )
    servidor_texto = models.CharField("servidor (texto original)", max_length=300, blank=True)
    unidade = models.CharField("unidade", max_length=200, blank=True)
    quantidade_publico = models.PositiveIntegerField("quantidade de público", blank=True, null=True)
    briefing = models.TextField("briefing", blank=True)
    materia_site = models.TextField("matéria no site", blank=True)
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
        verbose_name = "demanda de evento"
        verbose_name_plural = "demandas de eventos"
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
        return f"Demanda #{self.pk} — {self.tipo_evento}"

    def clean(self):
        super().clean()
        if (
            self.data_inicio_evento
            and self.data_fim_evento
            and self.data_fim_evento < self.data_inicio_evento
        ):
            raise ValidationError({"data_fim_evento": "A data final não pode ser anterior à inicial."})
