"""Cadastros do domínio de viagens, portados da Central de Viagens 3.

Diferenças deliberadas em relação à origem, registradas para quem comparar os
dois códigos (ver ``docs/PLANO_MESTRE_UNIFICACAO.md``):

- **Sem ``area``.** A origem é multi-tenant e pareia cada unicidade em duas
  constraints condicionais (global e por área). Aqui o sistema é único, então
  cada regra vira **uma** constraint global — a versão mais forte.
- **Placa única no sistema.** Na origem a placa é única por área (defeito
  ``DB-05`` de lá, que só existe porque há áreas). Sem áreas, duas viaturas com
  a mesma placa são sempre o mesmo veículo cadastrado duas vezes.
- **``faixa`` da tabela de diárias continua sendo ``choices``**, e não uma FK
  para ``cadastros.Regiao``, ainda que as três regiões operacionais coincidam
  com as três faixas. Dinheiro não pode depender de um catálogo que o
  administrador renomeia ou inativa pela tela; ``faixa_da_regiao()`` faz a
  ponte entre os dois.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

from core.models import ModeloTemporal

from .normalizacao import (
    RG_NAO_POSSUI,
    RG_NAO_POSSUI_EXIBICAO,
    formatar_cpf,
    formatar_placa,
    formatar_rg,
    formatar_telefone,
    exibir,
    normalizar_digitos,
    normalizar_maiusculas,
    normalizar_placa,
    normalizar_rg,
    placa_valida,
)


class OrigemLegado(models.Model):
    """Rastro da linha de origem em cargas vindas de outro sistema.

    É a chave de idempotência das migrações de dados: reexecutar a carga
    atualiza a linha existente em vez de duplicá-la, e permite desfazer
    exatamente o que foi importado.
    """

    legado_origem = models.CharField("origem no legado", max_length=50, blank=True)
    legado_pk = models.PositiveIntegerField("id no legado", blank=True, null=True)

    class Meta:
        abstract = True


class Unidade(ModeloTemporal):
    """Lotação: delegacia, divisão ou setor ao qual servidor e viatura pertencem."""

    nome = models.CharField("nome", max_length=255, unique=True)
    sigla = models.CharField("sigla", max_length=50, blank=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "unidade"
        verbose_name_plural = "unidades"

    def __str__(self):
        return self.sigla or self.nome

    def save(self, *args, **kwargs):
        self.nome = normalizar_maiusculas(self.nome)
        self.sigla = normalizar_maiusculas(self.sigla)
        super().save(*args, **kwargs)


class CatalogoComPadrao(ModeloTemporal):
    """Catálogo simples cujo item marcado como padrão vem pré-selecionado.

    Só um item pode ser o padrão: marcar um novo rebaixa o anterior na mesma
    transação, em vez de deixar a gravação estourar na constraint.
    """

    nome = models.CharField("nome", max_length=120, unique=True)
    is_padrao = models.BooleanField("padrão", default=False)

    class Meta:
        abstract = True
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.nome = normalizar_maiusculas(self.nome)
        if self.is_padrao:
            type(self).objects.select_for_update().exclude(pk=self.pk).filter(
                is_padrao=True
            ).update(is_padrao=False)
        super().save(*args, **kwargs)


class Cargo(CatalogoComPadrao):
    class Meta(CatalogoComPadrao.Meta):
        abstract = False
        verbose_name = "cargo"
        verbose_name_plural = "cargos"
        constraints = [
            models.UniqueConstraint(
                fields=["is_padrao"],
                condition=Q(is_padrao=True),
                name="viagens_cargo_padrao_unico",
            ),
        ]


class Combustivel(CatalogoComPadrao):
    class Meta(CatalogoComPadrao.Meta):
        abstract = False
        verbose_name = "combustível"
        verbose_name_plural = "combustíveis"
        constraints = [
            models.UniqueConstraint(
                fields=["is_padrao"],
                condition=Q(is_padrao=True),
                name="viagens_combustivel_padrao_unico",
            ),
        ]


class Servidor(ModeloTemporal, OrigemLegado):
    """A pessoa do domínio de viagens — inclusive quem dirige.

    Não existe cadastro de "motorista": motorista é um papel que um servidor
    exerce (``Viatura.motoristas``, ``SolicitacaoEvento.motorista``). Manter
    duas tabelas de pessoa levava o mesmo servidor a existir duas vezes, com
    grafias diferentes e sem CPF em uma delas.
    """

    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        COMPLETO = "COMPLETO", "Completo"

    nome = models.CharField("nome", max_length=255)
    status = models.CharField(
        "situação do cadastro",
        max_length=20,
        choices=Status.choices,
        default=Status.RASCUNHO,
        editable=False,
    )
    cargo = models.ForeignKey(
        Cargo,
        verbose_name="cargo",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="servidores",
    )
    cpf = models.CharField("CPF", max_length=11, blank=True)
    rg = models.CharField("RG", max_length=30, blank=True)
    sem_rg = models.BooleanField("não possui RG", default=False, editable=False)
    telefone = models.CharField("telefone", max_length=11, blank=True)
    unidade = models.ForeignKey(
        Unidade,
        verbose_name="unidade",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="servidores",
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "servidor"
        verbose_name_plural = "servidores"
        constraints = [
            models.UniqueConstraint(fields=["nome"], name="viagens_servidor_nome_unico"),
            # Documentos vazios não colidem entre si: vários servidores podem
            # estar sem CPF, mas dois com o mesmo CPF são a mesma pessoa.
            models.UniqueConstraint(
                fields=["cpf"],
                condition=~Q(cpf=""),
                name="viagens_servidor_cpf_unico",
            ),
            models.UniqueConstraint(
                fields=["rg"],
                condition=~Q(rg="") & ~Q(rg=RG_NAO_POSSUI),
                name="viagens_servidor_rg_unico",
            ),
            models.UniqueConstraint(
                fields=["telefone"],
                condition=~Q(telefone=""),
                name="viagens_servidor_telefone_unico",
            ),
            models.UniqueConstraint(
                fields=["legado_origem", "legado_pk"],
                condition=Q(legado_pk__isnull=False),
                name="viagens_servidor_legado_unico",
            ),
        ]

    def __str__(self):
        return self.nome

    @property
    def cpf_formatado(self):
        return exibir(self.cpf, formatar_cpf)

    @property
    def rg_formatado(self):
        return exibir(RG_NAO_POSSUI if self.sem_rg else self.rg, formatar_rg)

    @property
    def telefone_formatado(self):
        return exibir(self.telefone, formatar_telefone)

    def esta_completo(self):
        """Cadastro com o mínimo para figurar em documento oficial.

        Não bloqueia o CRUD: o cadastro pode nascer incompleto e ser
        completado depois; o status só sinaliza isso nas telas.
        """
        if not (self.nome or "").strip() or not self.cargo_id:
            return False
        if len(self.cpf or "") != 11:
            return False
        return self.sem_rg or bool(self.rg and self.rg != RG_NAO_POSSUI)

    def save(self, *args, **kwargs):
        self.nome = normalizar_maiusculas(self.nome)
        self.cpf = normalizar_digitos(self.cpf)
        rg = (self.rg or "").strip()
        # Aceita a marca escrita como se lê ("NÃO POSSUI RG"): sem isso ela
        # viraria o RG literal "NÃOPOSSUIRG", único, e o segundo servidor sem
        # RG não conseguiria ser gravado.
        self.sem_rg = not rg or rg.upper() in {RG_NAO_POSSUI, RG_NAO_POSSUI_EXIBICAO}
        self.rg = RG_NAO_POSSUI if self.sem_rg else normalizar_rg(rg)
        self.telefone = normalizar_digitos(self.telefone)
        self.status = self.Status.COMPLETO if self.esta_completo() else self.Status.RASCUNHO
        super().save(*args, **kwargs)


class Viatura(ModeloTemporal):
    """Veículo oficial que pode ser designado a uma viagem."""

    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        COMPLETO = "COMPLETO", "Completo"

    class Tipo(models.TextChoices):
        CARACTERIZADA = "CARACTERIZADA", "Caracterizada"
        DESCARACTERIZADA = "DESCARACTERIZADA", "Descaracterizada"

    placa = models.CharField("placa", max_length=7, unique=True)
    status = models.CharField(
        "situação do cadastro",
        max_length=20,
        choices=Status.choices,
        default=Status.RASCUNHO,
        editable=False,
    )
    modelo = models.CharField("modelo", max_length=120, blank=True)
    combustivel = models.ForeignKey(
        Combustivel,
        verbose_name="combustível",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="viaturas",
    )
    tipo = models.CharField(
        "tipo", max_length=20, choices=Tipo.choices, blank=True
    )
    unidade = models.ForeignKey(
        Unidade,
        verbose_name="unidade",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="viaturas",
    )
    motoristas = models.ManyToManyField(
        Servidor,
        verbose_name="motoristas",
        blank=True,
        related_name="viaturas_que_dirige",
    )

    class Meta:
        ordering = ["placa"]
        verbose_name = "viatura"
        verbose_name_plural = "viaturas"

    def __str__(self):
        return self.placa_formatada

    @property
    def placa_formatada(self):
        return formatar_placa(self.placa)

    def esta_completo(self):
        return bool(
            placa_valida(self.placa)
            and (self.modelo or "").strip()
            and self.combustivel_id
            and self.tipo
        )

    def clean(self):
        super().clean()
        placa = normalizar_placa(self.placa)
        if placa and not placa_valida(placa):
            raise ValidationError(
                {"placa": "Informe uma placa válida (ABC1234 ou ABC1D23)."}
            )

    def save(self, *args, **kwargs):
        self.placa = normalizar_placa(self.placa)
        self.modelo = normalizar_maiusculas(self.modelo)
        self.status = self.Status.COMPLETO if self.esta_completo() else self.Status.RASCUNHO
        super().save(*args, **kwargs)


class TabelaDiaria(ModeloTemporal):
    """Valor da diária por faixa, vigente a partir de uma data.

    O operador informa **apenas o valor de 24 horas**; 15% e 30% são derivados
    e gravados. Guardar os três congela o valor que valeu: mudar a regra de
    arredondamento amanhã não pode alterar o que já foi pago ontem.

    ``vigente_em`` devolve ``None`` quando não há vigência iniciada até a data,
    em vez de cair num valor padrão — cobrar com valor inventado é pior que
    falhar de forma visível.
    """

    PERCENTUAL_15 = Decimal("0.15")
    PERCENTUAL_30 = Decimal("0.30")
    CENTAVOS = Decimal("0.01")

    class Faixa(models.TextChoices):
        INTERIOR = "INTERIOR", "Interior"
        CAPITAL = "CAPITAL", "Capital"
        BRASILIA = "BRASILIA", "Brasília"

    faixa = models.CharField("faixa", max_length=20, choices=Faixa.choices)
    vigencia_inicio = models.DateField(
        "vigente a partir de",
        help_text="Viagens com saída a partir desta data usam estes valores.",
    )
    valor_24h = models.DecimalField("diária de 24 horas", max_digits=10, decimal_places=2)
    valor_15 = models.DecimalField("15%", max_digits=10, decimal_places=2, editable=False)
    valor_30 = models.DecimalField("30%", max_digits=10, decimal_places=2, editable=False)

    class Meta:
        ordering = ["-vigencia_inicio", "faixa"]
        verbose_name = "tabela de diárias"
        verbose_name_plural = "tabelas de diárias"
        constraints = [
            models.UniqueConstraint(
                fields=["faixa", "vigencia_inicio"],
                name="viagens_tabela_diaria_faixa_vigencia_unica",
            ),
            models.CheckConstraint(
                condition=Q(valor_24h__gt=0),
                name="viagens_tabela_diaria_valor_24h_positivo",
            ),
            # Os derivados também são defendidos: um `update()` cru ou uma
            # migração de dados grava sem passar pelo `save()` que os calcula.
            models.CheckConstraint(
                condition=Q(valor_15__gt=0),
                name="viagens_tabela_diaria_valor_15_positivo",
            ),
            models.CheckConstraint(
                condition=Q(valor_30__gt=0),
                name="viagens_tabela_diaria_valor_30_positivo",
            ),
        ]
        indexes = [
            models.Index(
                fields=["faixa", "-vigencia_inicio"],
                name="viagens_tabdiaria_busca_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_faixa_display()} — a partir de {self.vigencia_inicio:%d/%m/%Y}"

    @classmethod
    def derivar(cls, valor_24h):
        """(15%, 30%) de ``valor_24h``, em centavos, arredondando meio para cima."""
        base = Decimal(valor_24h)
        return (
            (base * cls.PERCENTUAL_15).quantize(cls.CENTAVOS, rounding=ROUND_HALF_UP),
            (base * cls.PERCENTUAL_30).quantize(cls.CENTAVOS, rounding=ROUND_HALF_UP),
        )

    @classmethod
    def vigente_em(cls, faixa, data):
        """Tabela da faixa vigente na data — a mais recente que já começou."""
        return (
            cls.objects.filter(faixa=faixa, vigencia_inicio__lte=data)
            .order_by("-vigencia_inicio")
            .first()
        )

    def save(self, *args, **kwargs):
        self.valor_15, self.valor_30 = self.derivar(self.valor_24h)
        super().save(*args, **kwargs)


def faixa_da_regiao(regiao):
    """Faixa de diária correspondente a uma ``cadastros.Regiao``, ou ``None``.

    As três regiões operacionais (Capital, Interior, Brasília) coincidem com as
    três faixas, mas a região é um cadastro editável e a faixa é um valor fixo:
    a ponte é feita aqui, por nome normalizado, e devolve ``None`` quando a
    região não corresponde a faixa nenhuma — quem chama decide o que fazer.
    """
    if regiao is None:
        return None
    nome = normalizar_maiusculas(getattr(regiao, "nome", regiao))
    nome = nome.replace("Í", "I").replace("Á", "A")
    for faixa in TabelaDiaria.Faixa:
        if faixa.value == nome:
            return faixa.value
    return None
