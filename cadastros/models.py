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
    class Meta(CadastroBase.Meta):
        verbose_name = "tipo de evento"
        verbose_name_plural = "tipos de evento"


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


class Estado(CadastroBase):
    sigla = models.CharField("sigla", max_length=2, unique=True)
    codigo_ibge = models.PositiveSmallIntegerField("código IBGE", unique=True)

    class Meta(CadastroBase.Meta):
        verbose_name = "estado"
        verbose_name_plural = "estados"


class Municipio(CadastroBase):
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

    class Meta(CadastroBase.Meta):
        verbose_name = "município"
        verbose_name_plural = "municípios"
        constraints = [
            models.UniqueConstraint(fields=["nome", "estado"], name="municipio_unico_por_estado"),
        ]


class Motorista(CadastroBase):
    telefone = models.CharField("telefone", max_length=30, blank=True)

    class Meta(CadastroBase.Meta):
        verbose_name = "motorista"
        verbose_name_plural = "motoristas"


class UnidadeMovel(CadastroBase):
    """Veículos de unidade móvel disponíveis para designar aos eventos."""

    class Meta(CadastroBase.Meta):
        verbose_name = "unidade móvel"
        verbose_name_plural = "unidades móveis"
