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
    descricao = models.TextField("descrição", blank=True)

    class Meta(CadastroBase.Meta):
        verbose_name = "serviço"
        verbose_name_plural = "serviços"


class Equipe(CadastroBase):
    class Meta(CadastroBase.Meta):
        verbose_name = "equipe"
        verbose_name_plural = "equipes"


class OrgaoResponsavel(CadastroBase):
    sigla = models.CharField("sigla", max_length=20, blank=True)

    class Meta(CadastroBase.Meta):
        verbose_name = "órgão responsável"
        verbose_name_plural = "órgãos responsáveis"


class Regiao(CadastroBase):
    class Meta(CadastroBase.Meta):
        verbose_name = "região"
        verbose_name_plural = "regiões"


class Municipio(CadastroBase):
    nome = models.CharField("nome", max_length=150)
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
            models.UniqueConstraint(fields=["nome", "regiao"], name="municipio_unico_por_regiao"),
        ]


class Motorista(CadastroBase):
    telefone = models.CharField("telefone", max_length=30, blank=True)

    class Meta(CadastroBase.Meta):
        verbose_name = "motorista"
        verbose_name_plural = "motoristas"
