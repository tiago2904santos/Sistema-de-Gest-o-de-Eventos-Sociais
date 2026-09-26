"""Ordem de serviço, portada do Gerenciador de Viagens com os mesmos campos.

Não tem viatura, roteiro, protocolo nem status próprios: tudo isso vem dos
ofícios vinculados. A numeração é por ano — a menor lacuna liberada por
exclusão primeiro, senão o maior número mais um — reservada pelo mecanismo
compartilhado de `core.numeracao`.
"""

from django.db import models, transaction
from django.utils import timezone

from core.constraints import periodo_ordenado
from core.legado import OrigemLegado
from core.models import ModeloCancelavel, ModeloTemporal

CONSTRAINT_NUMERO_ORDEM_SERVICO = "viagens_ordem_servico_ano_numero_unique"


class OrdemServico(ModeloTemporal, ModeloCancelavel, OrigemLegado):
    TIPO_PADRAO = "PADRAO"
    TIPO_OPERACAO_RETORNO_POSTERIOR = "OPERACAO_RETORNO_POSTERIOR"
    TIPO_CAMINHAO = "CAMINHAO"
    TIPO_MICROONIBUS = "MICROONIBUS"
    TIPO_CERIMONIAL_ANTECIPADO = "CERIMONIAL_ANTECIPADO"

    FUNCAO_CONDUCAO = "CONDUCAO"
    FUNCAO_TECNICO = "TECNICO"
    FUNCAO_APOIO = "APOIO"
    FUNCAO_COORDENACAO = "COORDENACAO"
    FUNCAO_PREPARACAO = "PREPARACAO"

    FUNCAO_SERVIDOR_CHOICES = [
        (FUNCAO_CONDUCAO, "Condução"),
        (FUNCAO_TECNICO, "Técnico"),
        (FUNCAO_APOIO, "Apoio"),
        (FUNCAO_COORDENACAO, "Coordenação"),
        (FUNCAO_PREPARACAO, "Preparação"),
    ]

    TIPO_NECESSIDADE_CHOICES = [
        (TIPO_PADRAO, "Padrão / texto livre"),
        (TIPO_OPERACAO_RETORNO_POSTERIOR, "Operação policial - um dia posterior"),
        (TIPO_CAMINHAO, "Caminhão - dois dias antes e depois"),
        (TIPO_MICROONIBUS, "Micro-ônibus"),
        (TIPO_CERIMONIAL_ANTECIPADO, "Cerimonial - ida antecipada"),
    ]

    # Tipos em que a equipe recebe função (condução, técnico, apoio...).
    TIPOS_COM_FUNCOES = (TIPO_CAMINHAO, TIPO_MICROONIBUS, TIPO_CERIMONIAL_ANTECIPADO)

    numero = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    ano = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    viagem = models.ForeignKey(
        "viagens_viagem.Viagem", on_delete=models.CASCADE, null=True, blank=True,
        related_name="ordens_servico", verbose_name="Viagem",
    )
    oficios = models.ManyToManyField(
        "viagens_oficios.Oficio", blank=True, related_name="ordens_servico", verbose_name="Ofícios vinculados",
    )
    data_evento_inicio = models.DateField("Data inicial do evento", null=True, blank=True)
    data_evento_fim = models.DateField("Data final do evento", null=True, blank=True)
    # Com ordem: a tela deixa arrastar os destinos, e o primeiro é o principal.
    destinos = models.ManyToManyField(
        "cadastros.Municipio", blank=True, related_name="ordens_servico", verbose_name="Destinos",
        through="OrdemServicoDestino",
    )
    servidores = models.ManyToManyField(
        "viagens_cadastros.Servidor", blank=True, related_name="ordens_servico", verbose_name="Servidores",
    )
    tipo_necessidade = models.CharField(
        "Tipo de necessidade", max_length=40, choices=TIPO_NECESSIDADE_CHOICES, default=TIPO_PADRAO,
    )
    # Papéis fixos da origem: continuam gravados para as OS antigas e como
    # reserva do texto do documento quando `funcoes_servidores` está vazio.
    motorista_equipe = models.ForeignKey(
        "viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Motorista",
    )
    tecnico_equipe = models.ForeignKey(
        "viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Técnico",
    )
    apoio_montagem = models.ForeignKey(
        "viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Apoio de montagem",
    )
    apoio_escolta = models.ForeignKey(
        "viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Apoio de escolta",
    )
    coordenador_cerimonial = models.ForeignKey(
        "viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Coordenação de cerimonial",
    )
    apoio_cerimonial = models.ForeignKey(
        "viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Apoio de cerimonial",
    )
    apoio_preparacao = models.ForeignKey(
        "viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Apoio de preparação",
    )
    # {"<servidor_id>": "<FUNCAO>"} — a função de cada um da equipe.
    funcoes_servidores = models.JSONField("Funções dos servidores", blank=True, default=dict)
    motivo = models.TextField("Motivo", blank=True, default="")

    class Meta:
        ordering = ["-ano", "-numero"]
        verbose_name = "Ordem de Serviço"
        verbose_name_plural = "Ordens de Serviço"
        constraints = [
            models.UniqueConstraint(
                fields=["legado_origem", "legado_pk"],
                condition=models.Q(legado_pk__isnull=False),
                name="f6_ordemservico_origem",
            ),
            models.UniqueConstraint(
                fields=["ano", "numero"],
                condition=models.Q(ano__isnull=False, numero__isnull=False),
                name=CONSTRAINT_NUMERO_ORDEM_SERVICO,
            ),
            periodo_ordenado("data_evento_inicio", "data_evento_fim", name="os_periodo_ordenado"),
        ]

    def __str__(self):
        return self.numero_formatado

    @property
    def numero_formatado(self):
        if self.numero and self.ano:
            return f"OS {self.numero:03d}/{self.ano}"
        return f"OS #{self.pk or 'nova'}"

    @property
    def periodo_display(self):
        if not self.data_evento_inicio:
            return "Período não informado"
        inicio = self.data_evento_inicio.strftime("%d/%m/%Y")
        if not self.data_evento_fim or self.data_evento_fim == self.data_evento_inicio:
            return inicio
        return f"{inicio} a {self.data_evento_fim.strftime('%d/%m/%Y')}"

    def definir_destinos(self, municipio_ids):
        """Grava os destinos na ordem recebida (o primeiro é o principal)."""
        OrdemServicoDestino.objects.filter(ordemservico=self).delete()
        OrdemServicoDestino.objects.bulk_create([
            OrdemServicoDestino(ordemservico=self, municipio_id=pk, ordem=posicao)
            for posicao, pk in enumerate(dict.fromkeys(municipio_ids), start=1)
        ])

    def destinos_em_ordem(self):
        """Destinos na ordem definida na tela (o principal primeiro)."""
        return self.destinos.select_related("estado").order_by(
            "ordemservicodestino__ordem", "ordemservicodestino__pk"
        )

    @property
    def destinos_display(self):
        if not self.pk:
            return "Sem destino"
        cache = getattr(self, "_prefetched_objects_cache", {}) or {}
        if "destinos" in cache:
            destinos = list(self.destinos.all())[:3]
        else:
            destinos = list(self.destinos_em_ordem()[:3])
        nomes = [f"{d.nome}/{d.estado.sigla}" for d in destinos]
        return ", ".join(nomes) if nomes else "Sem destino"

    # ---- numeração: menor lacuna do ano, senão o maior número mais um ----
    def _numero_ocupado(self, numero):
        return OrdemServico.objects.filter(ano=self.ano, numero=numero).exclude(pk=self.pk).exists()

    @classmethod
    def proximo_numero_livre(cls, ano):
        """(número, pk da lacuna usada ou None), na regra do número de ofício
        (`core.numeracao.proximo_do_livro`): a menor lacuna do ano, senão o
        maior número mais um. A sequência é a mesma das OS do Coffee Break
        (livro único): os números de lá contam como ocupados."""
        from core.numeracao import NAMESPACE_ORDEM_SERVICO, numeros_externos, proximo_do_livro

        usados = set(cls.objects.filter(ano=ano).exclude(numero__isnull=True).values_list("numero", flat=True))
        usados |= numeros_externos(NAMESPACE_ORDEM_SERVICO, ano)
        lacunas = dict(OrdemServicoNumeroLacuna.objects.filter(ano=ano).values_list("numero", "pk"))
        numero = proximo_do_livro(usados=usados, lacunas=lacunas)
        return numero, lacunas.get(numero)

    def _escolher_numero(self):
        numero, self._lacuna_numeracao_id = OrdemServico.proximo_numero_livre(self.ano)
        return numero

    def save(self, *args, **kwargs):
        if self.numero:
            # Número digitado (como no ofício): vale no ano corrente e, se era
            # uma lacuna, ela deixa de ser.
            if not self.ano:
                self.ano = timezone.localdate().year
            super().save(*args, **kwargs)
            OrdemServicoNumeroLacuna.objects.filter(ano=self.ano, numero=self.numero).delete()
            return
        from core.numeracao import NAMESPACE_ORDEM_SERVICO, reservar_numero

        self.ano = timezone.localdate().year
        pk_original, adicionando = self.pk, self._state.adding

        def gravar(numero):
            self.numero = numero
            super(OrdemServico, self).save(*args, **kwargs)
            lacuna = getattr(self, "_lacuna_numeracao_id", None)
            if lacuna:
                OrdemServicoNumeroLacuna.objects.filter(pk=lacuna).delete()

        def limpar():
            self.numero = None
            self._lacuna_numeracao_id = None
            if adicionando:
                self.pk = pk_original
                self._state.adding = True

        with transaction.atomic():
            reservar_numero(
                namespace=NAMESPACE_ORDEM_SERVICO, ano=self.ano, modelo=OrdemServico,
                constraint=CONSTRAINT_NUMERO_ORDEM_SERVICO, escolher=self._escolher_numero,
                gravar=gravar, ja_ocupado=self._numero_ocupado, apos_colisao=limpar,
            )


class OrdemServicoDestino(models.Model):
    """Destino da OS com a posição. Usa a tabela do M2M antigo: as duas
    primeiras colunas são as mesmas (a carga do legado depende disso)."""

    ordemservico = models.ForeignKey(OrdemServico, on_delete=models.CASCADE)
    municipio = models.ForeignKey("cadastros.Municipio", on_delete=models.CASCADE)
    ordem = models.PositiveIntegerField("ordem", default=0)

    class Meta:
        db_table = "viagens_ordens_ordemservico_destinos"
        ordering = ["ordem", "pk"]
        unique_together = [("ordemservico", "municipio")]
        verbose_name = "Destino da Ordem de Serviço"
        verbose_name_plural = "Destinos da Ordem de Serviço"

    def __str__(self):
        return f"{self.ordem}. {self.municipio}"


class OrdemServicoNumeroLacuna(models.Model):
    """Número de OS liberado por exclusão; saltos manuais não entram aqui."""

    ano = models.PositiveIntegerField(db_index=True)
    numero = models.PositiveIntegerField()
    liberado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ano", "numero"]
        verbose_name = "Número de Ordem de Serviço liberado"
        verbose_name_plural = "Números de Ordem de Serviço liberados"
        constraints = [models.UniqueConstraint(fields=["ano", "numero"], name="os_lacuna_ano_numero_unique")]

    def __str__(self):
        return f"{self.numero:02d}/{self.ano}"
