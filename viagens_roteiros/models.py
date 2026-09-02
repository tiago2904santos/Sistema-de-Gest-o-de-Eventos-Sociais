"""Roteiro de viagem: por onde se passa, quando, e quanto isso vale em diárias.

Portado da Central de Viagens 3. Duas adaptações ao sistema unificado:

- **Destinos são ``cadastros.Municipio``**, o cadastro geográfico que já existe
  aqui, em vez do ``Cidade`` da origem.
- **O agrupador é a solicitação de evento**, e não o "evento" da origem: um
  roteiro pode nascer avulso ou vinculado a uma solicitação já deferida. É a
  ponte entre os dois domínios que a auditoria da unificação previu.

A rota calculada (GeoJSON, totais, fonte e quando foi calculada) fica gravada
no roteiro, como na origem, para o mapa reabrir desenhado. Uma assinatura do
percurso (sede + destinos, na ordem) diz se ela ainda corresponde ao que está
gravado: mudou o percurso sem recalcular, a rota fica "desatualizada".

A composição das diárias é gravada parcela a parcela em
``RoteiroDiariaComponente``. Ela é imutável por decisão: é o que explica um
pagamento anos depois, quando os valores vigentes já forem outros.
"""

from django.db import models

from core.constraints import nao_negativo, periodo_ordenado, positivo
from core.models import ModeloCancelavel, ModeloTemporal


class Roteiro(ModeloTemporal, ModeloCancelavel):
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        FINALIZADO = "FINALIZADO", "Finalizado"

    class Tipo(models.TextChoices):
        AVULSO = "AVULSO", "Avulso"
        EVENTO = "EVENTO", "De solicitação de evento"

    solicitacao = models.ForeignKey(
        "solicitacoes.SolicitacaoEvento",
        verbose_name="solicitação de evento",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="roteiros",
    )
    tipo = models.CharField(
        "tipo", max_length=20, choices=Tipo.choices, default=Tipo.AVULSO
    )
    status = models.CharField(
        "status", max_length=20, choices=Status.choices, default=Status.RASCUNHO
    )

    # Sede: de onde se sai e para onde se volta.
    origem_municipio = models.ForeignKey(
        "cadastros.Municipio",
        verbose_name="município sede",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="roteiros_como_sede",
    )

    saida_dt = models.DateTimeField("saída da sede", blank=True, null=True)
    chegada_dt = models.DateTimeField("chegada ao primeiro destino", blank=True, null=True)
    retorno_saida_dt = models.DateTimeField("saída para o retorno", blank=True, null=True)
    retorno_chegada_dt = models.DateTimeField("chegada de volta à sede", blank=True, null=True)

    quantidade_servidores = models.PositiveIntegerField("servidores", default=1)

    # Resultado do cálculo, congelado: o que valeu quando o roteiro foi
    # finalizado. `RoteiroDiariaComponente` guarda a composição que o explica.
    resumo_diarias = models.CharField("composição das diárias", max_length=120, blank=True)
    valor_diarias = models.DecimalField(
        "valor das diárias", max_digits=12, decimal_places=2, blank=True, null=True
    )
    valor_diarias_extenso = models.TextField("valor por extenso", blank=True)
    observacoes = models.TextField("observações", blank=True)

    # Rota calculada pelo serviço de rotas, para o mapa reabrir desenhado sem
    # nova consulta. `rota_assinatura` é o percurso (sede + destinos) que ela
    # descreve; quando o percurso gravado deixa de bater com ela, o status
    # passa a DESATUALIZADA e a tela pede o recálculo.
    class RotaStatus(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        CALCULADA = "CALCULADA", "Calculada"
        DESATUALIZADA = "DESATUALIZADA", "Desatualizada"

    rota_status = models.CharField(
        "situação da rota",
        max_length=20,
        choices=RotaStatus.choices,
        default=RotaStatus.PENDENTE,
    )
    rota_geojson = models.JSONField("geometria da rota", blank=True, null=True)
    rota_distancia_km = models.DecimalField(
        "distância da rota (km)", max_digits=10, decimal_places=2, blank=True, null=True
    )
    rota_duracao_min = models.PositiveIntegerField(
        "duração da rota (min)", blank=True, null=True
    )
    rota_fonte = models.CharField("fonte da rota", max_length=40, blank=True)
    rota_assinatura = models.CharField("assinatura do percurso", max_length=128, blank=True)
    rota_calculada_em = models.DateTimeField("rota calculada em", blank=True, null=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "roteiro"
        verbose_name_plural = "roteiros"
        indexes = [
            models.Index(fields=["status", "-criado_em"], name="roteiro_status_criado_idx"),
        ]
        constraints = [
            # Encadeadas: cada ponta do percurso vem depois da anterior. Só a
            # inversão é barrada — ida e volta no mesmo instante é degenerada,
            # não impossível.
            periodo_ordenado(
                "saida_dt",
                "chegada_dt",
                name="roteiro_saida_antes_da_chegada",
                mensagem="A chegada ao destino não pode ser anterior à saída da sede.",
            ),
            periodo_ordenado(
                "chegada_dt",
                "retorno_saida_dt",
                name="roteiro_chegada_antes_do_retorno",
                mensagem="A saída de retorno não pode ser anterior à chegada ao destino.",
            ),
            periodo_ordenado(
                "retorno_saida_dt",
                "retorno_chegada_dt",
                name="roteiro_retorno_ordenado",
                mensagem="A chegada de volta não pode ser anterior à saída de retorno.",
            ),
            periodo_ordenado(
                "saida_dt",
                "retorno_chegada_dt",
                name="roteiro_periodo_total_ordenado",
                mensagem="A volta à sede não pode ser anterior à saída.",
            ),
            nao_negativo("valor_diarias", name="roteiro_valor_diarias_nao_negativo"),
            nao_negativo("rota_distancia_km", name="roteiro_rota_distancia_nao_negativa"),
        ]

    def __str__(self):
        destino = self.destinos.first()
        rotulo = destino.municipio if destino else "sem destino"
        return f"Roteiro {self.pk} — {rotulo}"

    @property
    def sede_cidade(self):
        return self.origem_municipio.nome if self.origem_municipio_id else ""

    @property
    def sede_uf(self):
        return self.origem_municipio.estado.sigla if self.origem_municipio_id else ""


class RoteiroDestino(ModeloTemporal):
    """Um destino do roteiro, na ordem em que é visitado."""

    roteiro = models.ForeignKey(
        Roteiro, on_delete=models.CASCADE, related_name="destinos"
    )
    municipio = models.ForeignKey(
        "cadastros.Municipio",
        verbose_name="município",
        on_delete=models.PROTECT,
        related_name="roteiro_destinos",
    )
    ordem = models.PositiveIntegerField("ordem", default=1)

    class Meta:
        ordering = ["ordem", "pk"]
        verbose_name = "destino do roteiro"
        verbose_name_plural = "destinos do roteiro"
        constraints = [
            models.UniqueConstraint(
                fields=["roteiro", "ordem"], name="roteiro_destino_ordem_unica"
            ),
        ]

    def __str__(self):
        return f"{self.ordem}. {self.municipio}"


class RoteiroTrecho(ModeloTemporal):
    """Um deslocamento entre dois municípios, com horários e quilometragem.

    A duração total é o tempo de viagem (estimado pelo serviço de rotas) mais
    o tempo adicional que o operador acrescenta — espera, pedágio, parada. As
    duas parcelas ficam gravadas em separado para a tela reabrir o trecho como
    foi montado, em vez de só o total.
    """

    class Sentido(models.TextChoices):
        IDA = "IDA", "Ida"
        RETORNO = "RETORNO", "Retorno"

    roteiro = models.ForeignKey(
        Roteiro, on_delete=models.CASCADE, related_name="trechos"
    )
    ordem = models.PositiveIntegerField("ordem", default=1)
    sentido = models.CharField(
        "sentido", max_length=10, choices=Sentido.choices, default=Sentido.IDA
    )
    origem_municipio = models.ForeignKey(
        "cadastros.Municipio",
        verbose_name="origem",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="trechos_como_origem",
    )
    destino_municipio = models.ForeignKey(
        "cadastros.Municipio",
        verbose_name="destino",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="trechos_como_destino",
    )
    saida_dt = models.DateTimeField("saída", blank=True, null=True)
    chegada_dt = models.DateTimeField("chegada", blank=True, null=True)
    distancia_km = models.DecimalField(
        "distância (km)", max_digits=8, decimal_places=2, blank=True, null=True
    )
    duracao_min = models.PositiveIntegerField(
        "duração (min)", blank=True, null=True
    )
    tempo_viagem_min = models.PositiveIntegerField(
        "tempo de viagem (min)", blank=True, null=True
    )
    tempo_adicional_min = models.PositiveIntegerField(
        "tempo adicional (min)", default=0
    )
    rota_fonte = models.CharField("fonte da estimativa", max_length=40, blank=True)

    class Meta:
        ordering = ["ordem", "pk"]
        verbose_name = "trecho do roteiro"
        verbose_name_plural = "trechos do roteiro"
        constraints = [
            models.UniqueConstraint(
                fields=["roteiro", "ordem"], name="roteiro_trecho_ordem_unica"
            ),
            periodo_ordenado(
                "saida_dt",
                "chegada_dt",
                name="roteiro_trecho_periodo_ordenado",
                mensagem="A chegada do trecho não pode ser anterior à saída.",
            ),
            nao_negativo("distancia_km", name="roteiro_trecho_distancia_nao_negativa"),
        ]

    def __str__(self):
        return f"{self.ordem}. {self.origem_municipio} → {self.destino_municipio}"


class RoteiroDiariaComponente(ModeloTemporal):
    """Uma parcela do total de diárias, com o valor que valeu quando foi paga.

    Imutável de propósito: é a explicação do pagamento. Recalcular o roteiro
    apaga as parcelas e grava outras — o que não se faz é editar uma parcela
    existente, porque isso reescreveria a história do que já foi pago.
    """

    class Origem(models.TextChoices):
        CALCULO = "CALCULO", "Calculada"
        LEGADO = "LEGADO", "Importada do legado"

    roteiro = models.ForeignKey(
        Roteiro, on_delete=models.CASCADE, related_name="componentes_diarias"
    )
    tabela_diaria = models.ForeignKey(
        "viagens_cadastros.TabelaDiaria",
        verbose_name="vigência aplicada",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )
    ordem = models.PositiveIntegerField("ordem", default=1)
    origem = models.CharField(
        "origem", max_length=12, choices=Origem.choices, default=Origem.CALCULO
    )
    faixa = models.CharField("faixa", max_length=20)
    percentual = models.PositiveSmallIntegerField(
        "percentual", choices=[(15, "15%"), (30, "30%"), (100, "100%")]
    )
    quantidade = models.PositiveIntegerField("quantidade", default=1)
    valor_unitario = models.DecimalField("valor unitário", max_digits=10, decimal_places=2)
    subtotal = models.DecimalField("subtotal", max_digits=12, decimal_places=2)
    tabela_vigencia_inicio = models.DateField("vigência a partir de", blank=True, null=True)
    periodo_inicio = models.DateTimeField("início do período", blank=True, null=True)
    periodo_fim = models.DateTimeField("fim do período", blank=True, null=True)

    class Meta:
        ordering = ["ordem", "pk"]
        verbose_name = "parcela de diária"
        verbose_name_plural = "parcelas de diária"
        indexes = [
            models.Index(
                fields=["percentual", "periodo_inicio"], name="roteiro_parcela_busca_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["roteiro", "ordem"], name="roteiro_parcela_ordem_unica"
            ),
            positivo("quantidade", name="roteiro_parcela_quantidade_positiva"),
            nao_negativo("valor_unitario", name="roteiro_parcela_valor_nao_negativo"),
            nao_negativo("subtotal", name="roteiro_parcela_subtotal_nao_negativo"),
            periodo_ordenado(
                "periodo_inicio", "periodo_fim", name="roteiro_parcela_periodo_ordenado"
            ),
        ]

    def __str__(self):
        return f"{self.quantidade} x {self.percentual}% ({self.faixa})"
