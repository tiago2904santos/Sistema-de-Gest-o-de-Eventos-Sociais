"""Modelos do atendimento à imprensa da ASCOM.

Espelham o "Relatório de atendimento": cada linha é um pedido de um
jornalista (veículo, contato, o que foi pedido), quem atendeu, as fontes
consultadas e a resposta enviada. Veículos e equipe são cadastros de apoio
para padronizar nomes e alimentar filtros e relatórios.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Responsavel(models.Model):
    """Integrante da equipe de atendimento à imprensa."""

    nome = models.CharField("nome", max_length=100, unique=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "responsável da equipe"
        verbose_name_plural = "responsáveis da equipe"

    def __str__(self):
        return self.nome


class Veiculo(models.Model):
    """Veículo de imprensa (RIC, RPC, Band, G1...)."""

    nome = models.CharField("nome", max_length=150, unique=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "veículo de imprensa"
        verbose_name_plural = "veículos de imprensa"

    def __str__(self):
        return self.nome


class SituacaoAtendimento(models.TextChoices):
    EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
    EM_ANDAMENTO_TEXTO = "EM_ANDAMENTO_TEXTO", "Em andamento — texto"
    EM_ANDAMENTO_VIDEO = "EM_ANDAMENTO_VIDEO", "Em andamento — vídeo"
    AGUARDANDO_FONTE = "AGUARDANDO_FONTE", "Aguardando fonte"
    AGUARDANDO_PRODUTORA = "AGUARDANDO_PRODUTORA", "Aguardando produtora"
    AGUARDAR_NOVA_SOLICITACAO = "AGUARDAR_NOVA_SOLICITACAO", "Aguardar nova solicitação"
    PROXIMO_MES = "PROXIMO_MES", "Próximo mês"
    ATENDIDO = "ATENDIDO", "Atendido"
    NAO_RESPONDER = "NAO_RESPONDER", "Não responder"


SITUACOES_ABERTAS = [
    SituacaoAtendimento.EM_ANDAMENTO,
    SituacaoAtendimento.EM_ANDAMENTO_TEXTO,
    SituacaoAtendimento.EM_ANDAMENTO_VIDEO,
    SituacaoAtendimento.AGUARDANDO_FONTE,
    SituacaoAtendimento.AGUARDANDO_PRODUTORA,
    SituacaoAtendimento.AGUARDAR_NOVA_SOLICITACAO,
    SituacaoAtendimento.PROXIMO_MES,
]

SITUACOES_ENCERRADAS = [
    SituacaoAtendimento.ATENDIDO,
    SituacaoAtendimento.NAO_RESPONDER,
]

CSS_SITUACAO = {
    SituacaoAtendimento.EM_ANDAMENTO: "em_andamento",
    SituacaoAtendimento.EM_ANDAMENTO_TEXTO: "em_andamento",
    SituacaoAtendimento.EM_ANDAMENTO_VIDEO: "em_andamento",
    SituacaoAtendimento.AGUARDANDO_FONTE: "aguardando",
    SituacaoAtendimento.AGUARDANDO_PRODUTORA: "aguardando",
    SituacaoAtendimento.AGUARDAR_NOVA_SOLICITACAO: "aguardando",
    SituacaoAtendimento.PROXIMO_MES: "pendente",
    SituacaoAtendimento.ATENDIDO: "atendido",
    SituacaoAtendimento.NAO_RESPONDER: "nao_responder",
}


class Atendimento(models.Model):
    """Pedido de um jornalista e o atendimento dado pela assessoria."""

    data = models.DateField("data do pedido")
    horario = models.TimeField("horário do pedido", blank=True, null=True)
    jornalista = models.CharField("jornalista", max_length=150)
    veiculo = models.ForeignKey(
        Veiculo,
        verbose_name="veículo",
        on_delete=models.PROTECT,
        related_name="atendimentos",
        blank=True,
        null=True,
    )
    contato = models.CharField("contato", max_length=150, blank=True)
    pedido = models.TextField("pedido")
    situacao = models.CharField(
        "situação",
        max_length=30,
        choices=SituacaoAtendimento.choices,
        default=SituacaoAtendimento.EM_ANDAMENTO,
    )
    responsavel = models.ForeignKey(
        Responsavel,
        verbose_name="responsável pelo atendimento",
        on_delete=models.PROTECT,
        related_name="atendimentos",
        blank=True,
        null=True,
    )
    deadline = models.DateField("deadline / veiculação", blank=True, null=True)
    horario_resposta = models.TimeField("horário da resposta", blank=True, null=True)
    responsavel_resposta = models.ForeignKey(
        Responsavel,
        verbose_name="responsável pela resposta",
        on_delete=models.PROTECT,
        related_name="atendimentos_respondidos",
        blank=True,
        null=True,
    )
    fonte = models.TextField(
        "fontes consultadas", blank=True,
        help_text="Uma fonte por linha (delegado, assessoria, unidade).",
    )
    inicio_pedido = models.TextField(
        "início do pedido às fontes", blank=True,
        help_text="Horário em que cada fonte foi acionada, uma por linha.",
    )
    final_pedido = models.TextField(
        "retorno das fontes", blank=True,
        help_text="Horário em que cada fonte respondeu, uma por linha.",
    )
    andamento = models.TextField("andamento", blank=True)
    resposta = models.TextField("resposta enviada", blank=True)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criado por",
        on_delete=models.PROTECT,
        related_name="atendimentos_imprensa_criados",
        blank=True,
        null=True,
    )
    chave_importacao = models.CharField(
        "chave da importação", max_length=64, unique=True, blank=True, null=True
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["-data", "-horario", "-pk"]
        verbose_name = "atendimento à imprensa"
        verbose_name_plural = "atendimentos à imprensa"
        indexes = [
            models.Index(fields=["situacao", "data"], name="atend_situacao_data_idx"),
            models.Index(fields=["deadline"], name="atend_deadline_idx"),
        ]

    def __str__(self):
        return f"{self.jornalista} — {self.data:%d/%m/%Y}"

    def clean(self):
        super().clean()
        if self.situacao == SituacaoAtendimento.ATENDIDO and not (
            self.resposta or self.andamento
        ):
            raise ValidationError(
                {"resposta": "Registre a resposta enviada (ou o andamento) ao marcar como atendido."}
            )

    @property
    def situacao_css(self):
        return CSS_SITUACAO.get(self.situacao, "pendente")

    @property
    def aberto(self):
        return self.situacao in SITUACOES_ABERTAS

    @property
    def atendido(self):
        return self.situacao == SituacaoAtendimento.ATENDIDO

    @property
    def pedido_resumo(self):
        texto = " ".join(self.pedido.split())
        return texto if len(texto) <= 90 else texto[:87].rstrip() + "…"

    @property
    def fontes_alinhadas(self):
        """Fontes com os horários de acionamento e retorno lado a lado.

        A planilha registra uma fonte por bloco (separados por linha em
        branco) nas três colunas; aqui elas são reunidas por posição.
        """

        def blocos(texto):
            partes = [
                " ".join(p.split()) for p in (texto or "").replace("\r", "").split("\n\n")
            ]
            return [p for p in partes if p]

        fontes = blocos(self.fonte)
        inicios = blocos(self.inicio_pedido)
        finais = blocos(self.final_pedido)
        if not fontes:
            return []
        linhas = []
        for indice, fonte in enumerate(fontes):
            linhas.append(
                {
                    "fonte": fonte,
                    "inicio": inicios[indice] if indice < len(inicios) else "",
                    "fim": finais[indice] if indice < len(finais) else "",
                }
            )
        return linhas
