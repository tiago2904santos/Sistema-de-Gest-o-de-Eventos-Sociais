"""A viagem: o agrupador OPCIONAL dos documentos de um deslocamento.

É o "Evento" do Gerenciador de Viagens, com outro nome: aqui "evento" já é a
demanda de evento social, e o que este modelo agrupa são os documentos de uma
viagem — ofícios, roteiros, planos de trabalho, ordens de serviço e termos.
Nunca é obrigatória: todo documento continua podendo nascer avulso no seu
próprio módulo.

Diferenças em relação à origem, todas de armazenamento (a tela é a mesma):
o destino guarda a chave do estado e do município (na origem era texto), os
destinos adicionais guardam as chaves em `destinos_extras`, e não há área de
trabalho nem pasta do Drive.
"""

from django.db import models
from django.utils import timezone

from core.constraints import periodo_ordenado
from core.legado import OrigemLegado
from core.models import ModeloCancelavel, ModeloTemporal
from core.normalizers import normalize_spaces
from core.uploads import validate_private_document_upload


class TipoViagem(ModeloTemporal, OrigemLegado):
    """Tipo de viagem: um ou mais por viagem; o título nasce deles."""

    nome = models.CharField("nome", max_length=120, unique=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Tipo de viagem"
        verbose_name_plural = "Tipos de viagem"
        constraints = [
            models.UniqueConstraint(
                fields=["legado_origem", "legado_pk"],
                condition=models.Q(legado_pk__isnull=False),
                name="f6_tipoviagem_origem",
            ),
        ]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = normalize_spaces(self.nome)
        super().save(*args, **kwargs)


class Viagem(ModeloTemporal, ModeloCancelavel, OrigemLegado):
    STATUS_RASCUNHO = "rascunho"
    STATUS_EM_PREPARACAO = "em_preparacao"
    STATUS_DOCUMENTOS_GERADOS = "documentos_gerados"
    STATUS_EM_EXECUCAO = "em_execucao"
    STATUS_FINALIZADO = "finalizado"
    STATUS_CANCELADO = "cancelado"
    STATUS_CHOICES = [
        (STATUS_RASCUNHO, "Rascunho"),
        (STATUS_EM_PREPARACAO, "Em preparação"),
        (STATUS_DOCUMENTOS_GERADOS, "Documentos gerados"),
        (STATUS_EM_EXECUCAO, "Em execução"),
        (STATUS_FINALIZADO, "Finalizado"),
        (STATUS_CANCELADO, "Cancelado"),
    ]

    titulo = models.CharField("Título", max_length=255, blank=True, default="")
    descricao = models.TextField("Descrição/objetivo", blank=True, default="")
    destino_estado = models.ForeignKey(
        "cadastros.Estado", on_delete=models.PROTECT, null=True, blank=True,
        related_name="+", verbose_name="UF do destino",
    )
    destino_municipio = models.ForeignKey(
        "cadastros.Municipio", on_delete=models.PROTECT, null=True, blank=True,
        related_name="viagens", verbose_name="Município do destino",
    )
    # Do segundo destino em diante: lista de {"estado": pk, "municipio": pk}.
    destinos_extras = models.JSONField("Destinos adicionais", default=list, blank=True)
    data_inicio = models.DateField("Data inicial", null=True, blank=True)
    data_fim = models.DateField("Data final", null=True, blank=True)
    horario_inicio = models.TimeField("Horário inicial", null=True, blank=True)
    horario_fim = models.TimeField("Horário final", null=True, blank=True)
    unidade_responsavel = models.ForeignKey(
        "viagens_cadastros.Unidade", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="viagens", verbose_name="Unidade responsável",
    )
    responsavel = models.ForeignKey(
        "viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="viagens_responsavel", verbose_name="Responsável",
    )
    tipos = models.ManyToManyField(TipoViagem, blank=True, related_name="viagens", verbose_name="Tipos da viagem")
    motivo = models.TextField("Motivo", blank=True, default="")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_RASCUNHO)
    # O "ambiente" da viagem: o setor (ex.: ASCOM) que vai executá-la. Nasce da
    # equipe que a DG designou na solicitação; define de onde vêm sede e prazos.
    setor = models.ForeignKey(
        "accounts.Setor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="viagens", verbose_name="Ambiente (setor)",
    )

    class Meta:
        ordering = ["-data_inicio", "-criado_em"]
        verbose_name = "Viagem"
        verbose_name_plural = "Viagens"
        constraints = [
            models.UniqueConstraint(
                fields=["legado_origem", "legado_pk"],
                condition=models.Q(legado_pk__isnull=False),
                name="f6_viagem_origem",
            ),
            periodo_ordenado("data_inicio", "data_fim", name="viagem_periodo_ordenado"),
        ]

    def __str__(self):
        return self.titulo or f"Viagem #{self.pk or 'nova'}"

    # Documentos que a viagem agrupa, na ordem em que o cancelamento os percorre.
    DOCUMENTOS = ("oficios", "ordens_servico", "planos_trabalho", "termos_autorizacao", "roteiros")

    @property
    def periodo_display(self):
        if not self.data_inicio:
            return "Período não informado"
        inicio = self.data_inicio.strftime("%d/%m/%Y")
        if not self.data_fim or self.data_fim == self.data_inicio:
            return inicio
        return f"{inicio} a {self.data_fim.strftime('%d/%m/%Y')}"

    @property
    def destino_display(self):
        if self.destino_municipio_id:
            m = self.destino_municipio
            return f"{m.nome}/{m.estado.sigla}"
        if self.destino_estado_id:
            return self.destino_estado.sigla
        return "Destino não informado"

    @property
    def tipos_display(self):
        if not self.pk:
            return ""
        return " / ".join(t.nome for t in self.tipos.all())

    def destinos_pares(self):
        """[(estado_id, municipio_id)] de todos os destinos, o principal primeiro."""
        pares = []
        if self.destino_estado_id or self.destino_municipio_id:
            pares.append((self.destino_estado_id, self.destino_municipio_id))
        for extra in self.destinos_extras or []:
            if isinstance(extra, dict):
                pares.append((extra.get("estado"), extra.get("municipio")))
        return pares

    def cancelar(self, motivo=""):
        """Cancela a viagem e, em cascata, os documentos dela ainda ativos."""
        self.status = self.STATUS_CANCELADO
        self.cancelado = True
        self.motivo_cancelamento = motivo
        self.cancelado_em = timezone.now()
        self.save(update_fields=["status", "cancelado", "motivo_cancelamento", "cancelado_em", "atualizado_em"])
        texto = f"Viagem cancelada: {motivo}" if motivo else "Viagem cancelada."
        for relacao in self.DOCUMENTOS:
            for documento in getattr(self, relacao).filter(cancelado=False):
                documento.cancelar(texto)

    def reativar(self):
        """Reativa a viagem e só os documentos cancelados por causa dela."""
        self.status = self.STATUS_RASCUNHO
        self.cancelado = False
        self.motivo_cancelamento = ""
        self.cancelado_em = None
        self.save(update_fields=["status", "cancelado", "motivo_cancelamento", "cancelado_em", "atualizado_em"])
        for relacao in self.DOCUMENTOS:
            for documento in getattr(self, relacao).filter(cancelado=True, motivo_cancelamento__startswith="Viagem cancelada"):
                documento.reativar()


class EquipePrevista(ModeloTemporal):
    """Quantos servidores de uma equipe a DG designou para esta viagem.

    É a meta do contador "designados x em ofícios": a viagem nasce da
    solicitação com "ASCOM: 2", e enquanto os ofícios dela não somarem dois
    servidores a tela avisa que falta gente. Quantidade vazia é equipe
    designada sem número — aparece, mas não conta para a meta.
    """

    viagem = models.ForeignKey(Viagem, on_delete=models.CASCADE, related_name="equipes_previstas")
    equipe = models.ForeignKey("cadastros.Equipe", on_delete=models.PROTECT, related_name="+", verbose_name="equipe")
    quantidade = models.PositiveIntegerField("servidores designados", null=True, blank=True)

    class Meta:
        ordering = ["equipe__nome"]
        verbose_name = "Equipe prevista da viagem"
        verbose_name_plural = "Equipes previstas da viagem"
        constraints = [
            models.UniqueConstraint(fields=["viagem", "equipe"], name="viagem_equipe_prevista_unica"),
        ]

    def __str__(self):
        if self.quantidade:
            return f"{self.equipe}: {self.quantidade}"
        return f"{self.equipe} (sem quantidade)"


VIAGEM_SOLICITACAO_EXTENSOES = ["pdf", "png", "jpg", "jpeg"]


def viagem_solicitacao_upload_to(instance, filename):
    return f"viagens/{instance.viagem_id or 'nova'}/solicitacoes/{filename}"


class ViagemDocumentoSolicitacao(ModeloTemporal, OrigemLegado):
    """Ofício solicitante, convite, despacho ou imagem anexados à viagem (sempre PDF)."""

    viagem = models.ForeignKey(Viagem, on_delete=models.CASCADE, related_name="documentos_solicitacao")
    # A mesma política dos outros anexos (m070); a tela também confere antes de converter.
    arquivo = models.FileField(upload_to=viagem_solicitacao_upload_to, validators=[validate_private_document_upload])
    nome_original = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["criado_em"]
        verbose_name = "Documento de solicitação da viagem"
        verbose_name_plural = "Documentos de solicitação da viagem"
        constraints = [
            models.UniqueConstraint(
                fields=["legado_origem", "legado_pk"],
                condition=models.Q(legado_pk__isnull=False),
                name="f6_viagemdocumentosolicitacao_origem",
            ),
        ]

    def __str__(self):
        return self.nome_original or str(self.arquivo)
