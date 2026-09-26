from core.legado import OrigemLegado
from django.db import models


class CadastroBase(models.Model):
    """Base para tabelas de apoio: nome + ativo + timestamps."""

    nome = models.CharField("nome", max_length=150, unique=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class TipoEvento(CadastroBase):
    """Tipo de evento e o modelo da solicitação desse tipo.

    O modelo (serviços, equipes com quantidade, solicitante, cargo e órgão
    padrão) é só sugestão: a tela da solicitação mostra e o usuário aplica
    com um clique — nada é preenchido sozinho.
    """

    servicos_sugeridos = models.ManyToManyField(
        "Servico",
        verbose_name="serviços sugeridos",
        related_name="tipos_evento_sugeridos",
        blank=True,
    )
    solicitante_padrao = models.CharField("solicitante padrão", max_length=150, blank=True)
    cargo_padrao = models.CharField("cargo / unidade padrão", max_length=255, blank=True)
    orgao_padrao = models.ForeignKey(
        "OrgaoResponsavel",
        verbose_name="órgão responsável padrão",
        on_delete=models.SET_NULL,
        related_name="tipos_evento_padrao",
        blank=True,
        null=True,
    )

    class Meta(CadastroBase.Meta):
        verbose_name = "tipo de evento"
        verbose_name_plural = "tipos de evento"

    @property
    def tem_modelo(self):
        return bool(
            self.solicitante_padrao
            or self.cargo_padrao
            or self.orgao_padrao_id
            or self.servicos_sugeridos.exists()
            or self.equipes_sugeridas.exists()
        )


class Servico(CadastroBase):
    class Meta(CadastroBase.Meta):
        verbose_name = "serviço"
        verbose_name_plural = "serviços"


class Equipe(CadastroBase):
    class Meta(CadastroBase.Meta):
        verbose_name = "equipe"
        verbose_name_plural = "equipes"


class OrgaoResponsavel(CadastroBase):
    class Meta(CadastroBase.Meta):
        verbose_name = "órgão responsável"
        verbose_name_plural = "órgãos responsáveis"


class Regiao(CadastroBase):
    class Meta(CadastroBase.Meta):
        verbose_name = "região"
        verbose_name_plural = "regiões"


class Estado(CadastroBase, OrigemLegado):
    sigla = models.CharField("sigla", max_length=2, unique=True)
    codigo_ibge = models.PositiveSmallIntegerField("código IBGE", unique=True)

    class Meta(CadastroBase.Meta):
        verbose_name = "estado"
        verbose_name_plural = "estados"
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_estado_origem")]


class Municipio(CadastroBase, OrigemLegado):
    capital = models.BooleanField("capital", default=False)

    nome = models.CharField("nome", max_length=150)
    codigo_ibge = models.PositiveIntegerField(
        "código IBGE", unique=True, blank=True, null=True
    )
    estado = models.ForeignKey(
        Estado,
        verbose_name="estado",
        on_delete=models.PROTECT,
        related_name="municipios",
    )
    regiao = models.ForeignKey(
        Regiao,
        verbose_name="região",
        on_delete=models.PROTECT,
        related_name="municipios",
    )
    # Coordenadas para o mapa e o cálculo de rota do módulo Viagens.
    # Opcionais: preenchidas por importação/geocodificação, nunca à mão.
    latitude = models.DecimalField(
        "latitude", max_digits=10, decimal_places=7, blank=True, null=True
    )
    longitude = models.DecimalField(
        "longitude", max_digits=10, decimal_places=7, blank=True, null=True
    )

    class Meta(CadastroBase.Meta):
        verbose_name = "município"
        verbose_name_plural = "municípios"
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_municipio_origem"),
            models.UniqueConstraint(fields=["nome", "estado"], name="municipio_unico_por_estado"),
        ]


class UnidadeMovel(CadastroBase):
    """Veículos de unidade móvel disponíveis para designar aos eventos."""

    class Meta(CadastroBase.Meta):
        verbose_name = "unidade móvel"
        verbose_name_plural = "unidades móveis"


class TextoDespacho(CadastroBase):
    """Texto pronto da observação do despacho da DG, inserido com um clique.

    O `nome` é o rótulo curto do botão; o `texto` é o que entra no campo.
    """

    texto = models.TextField("texto")

    class Meta(CadastroBase.Meta):
        verbose_name = "texto pronto do despacho"
        verbose_name_plural = "textos prontos do despacho"


class TipoEventoEquipe(models.Model):
    """Equipe que costuma acompanhar um tipo de evento, com a quantidade usual."""

    tipo_evento = models.ForeignKey(
        TipoEvento,
        verbose_name="tipo de evento",
        on_delete=models.CASCADE,
        related_name="equipes_sugeridas",
    )
    equipe = models.ForeignKey(
        Equipe,
        verbose_name="equipe",
        on_delete=models.CASCADE,
        related_name="tipos_evento_sugeridos",
    )
    quantidade = models.PositiveIntegerField("quantidade de servidores", blank=True, null=True)

    class Meta:
        verbose_name = "equipe sugerida do tipo de evento"
        verbose_name_plural = "equipes sugeridas do tipo de evento"
        ordering = ["equipe__nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_evento", "equipe"], name="equipe_sugerida_unica_por_tipo"
            ),
        ]

    def __str__(self):
        return f"{self.tipo_evento} — {self.equipe}"
