from core.legado import OrigemLegado
from django.db import models
from django.db.models import Q
from django.utils import timezone
from core.models import ModeloTemporal, ModeloCancelavel
from core.normalizers import normalize_spaces, normalize_upper
from core.utils.masks import normalize_protocolo
from viagens_cadastros.models import Servidor, Viatura, Unidade, Combustivel
from viagens_roteiros.models import Roteiro

CONSTRAINT_NUMERO_OFICIO = "viagens_oficio_ano_numero_unique"

class Oficio(ModeloTemporal, ModeloCancelavel, OrigemLegado):
    STATUS_RASCUNHO = "RASCUNHO"

    STATUS_GERADO = "GERADO"

    STATUS_FINALIZADO = "FINALIZADO"

    STATUS_ARQUIVADO = "ARQUIVADO"

    STATUS_CHOICES = [
        (STATUS_RASCUNHO, "Rascunho"),
        (STATUS_GERADO, "Gerado"),
        (STATUS_FINALIZADO, "Finalizado (legado)"),
        (STATUS_ARQUIVADO, "Arquivado"),
    ]

    CUSTEIO_UNIDADE_DPC = "UNIDADE_DPC"

    CUSTEIO_OUTRA_INSTITUICAO = "OUTRA_INSTITUICAO"

    CUSTEIO_ONUS_LIMITADO = "ONUS_LIMITADO"

    CUSTEIO_CHOICES = [
        (CUSTEIO_UNIDADE_DPC, "Unidade DPC"),
        (CUSTEIO_OUTRA_INSTITUICAO, "Outra instituição"),
        (CUSTEIO_ONUS_LIMITADO, "Ônus limitado"),
    ]

    numero = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    ano = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    data_criacao = models.DateField(default=timezone.localdate, db_index=True)

    protocolo = models.CharField(max_length=30, blank=True, default="", db_index=True)

    assunto = models.CharField(max_length=255, blank=True, default="")

    motivo = models.TextField(blank=True, default="")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RASCUNHO)

    roteiro = models.ForeignKey(
        Roteiro,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="oficios",
    )

    solicitante = models.ForeignKey(
        Unidade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    custeio = models.CharField(
        max_length=30,
        choices=CUSTEIO_CHOICES,
        default=CUSTEIO_UNIDADE_DPC,
    )

    custeio_observacao = models.CharField(max_length=255, blank=True, default="")

    servidores = models.ManyToManyField(Servidor, blank=True, related_name="oficios")

    diarias_quantidade_servidores = models.PositiveIntegerField(
        "Quantidade de servidores considerada nas diárias",
        null=True,
        blank=True,
        editable=False,
        help_text=(
            "Snapshot do efetivo usado no total de diárias; não muda quando um "
            "servidor é excluído posteriormente do cadastro."
        ),
    )

    servidores_termo_autorizacao = models.ManyToManyField(
        Servidor,
        blank=True,
        related_name="oficios_termo_autorizacao",
        verbose_name="Servidores com Termo de Autorização",
    )

    viatura = models.ForeignKey(
        Viatura,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="oficios",
    )

    motorista = models.ForeignKey(
        Servidor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="oficios_motorista",
    )

    porte_transporte_armas = models.BooleanField(
        default=True,
        verbose_name="Porte/transporte de armas",
    )

    transporte_placa_manual = models.CharField(max_length=7, blank=True, default="")

    transporte_modelo_manual = models.CharField(max_length=120, blank=True, default="")

    transporte_combustivel_manual = models.ForeignKey(
        Combustivel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    transporte_tipo_manual = models.CharField(
        max_length=20,
        choices=Viatura.Tipo.choices,
        blank=True,
        default="",
    )

    MOTORISTA_MODO_SERVIDOR = "SERVIDOR"

    MOTORISTA_MODO_MANUAL = "MANUAL"

    MOTORISTA_MODO_CHOICES = [
        (MOTORISTA_MODO_SERVIDOR, "Servidor"),
        (MOTORISTA_MODO_MANUAL, "Manual"),
    ]

    motorista_modo = models.CharField(
        max_length=10,
        choices=MOTORISTA_MODO_CHOICES,
        default=MOTORISTA_MODO_SERVIDOR,
    )

    motorista_manual_nome = models.CharField(max_length=255, blank=True, default="")

    motorista_manual_rg = models.CharField(max_length=30, blank=True, default="")

    motorista_manual_cpf = models.CharField(max_length=11, blank=True, default="")

    motorista_manual_cargo = models.CharField(max_length=120, blank=True, default="")

    motorista_manual_unidade = models.CharField(max_length=255, blank=True, default="")

    motorista_manual_observacao = models.TextField(blank=True, default="")

    motorista_oficio_referencia = models.CharField(
        max_length=16,
        blank=True,
        default="",
        verbose_name="Ofício do motorista",
        help_text="Referência no formato número/ano (ex.: 15/2026).",
    )

    motorista_protocolo_ref = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="Protocolo do motorista",
    )

    retificado_documento = models.BooleanField(
        default=False,
        verbose_name="Emitir como retificado",
        help_text="Quando verdadeiro e o ofício seria Autorização por datas, o documento usa o rótulo Retificado.",
    )

    complementar_documento = models.BooleanField(
        default=False,
        verbose_name="Emitir como complementar",
        help_text="Quando verdadeiro, o documento usa o rótulo Complementar ao lado do número do ofício.",
    )

    def __str__(self):
        return f"Ofício {self.numero_formatado}"

    @property
    def numero_formatado(self) -> str:
        if self.numero and self.ano:
            return f"{self.numero:02d}/{self.ano}"
        return "—"

    def diarias_para_servidores(self):
        """Diárias deste ofício = valor por servidor (persistido no roteiro) × nº de servidores.

        A F2 guarda o total da equipe no roteiro. O ofício aplica seu snapshot
        do efetivo aceito no passo de viajantes, para que uma exclusão posterior no
        cadastro não reescreva o valor de documento já emitido.
        """
        from decimal import ROUND_HALF_UP, Decimal

        from viagens_roteiros.services.valor_extenso import valor_por_extenso_ptbr

        roteiro = self.roteiro
        if not roteiro or roteiro.valor_diarias is None:
            return None

        # Registros anteriores à migração, instâncias ainda não salvas e fixtures
        # montadas diretamente continuam com fallback seguro para o efetivo vivo.
        qtd_servidores = self.diarias_quantidade_servidores
        if qtd_servidores is None:
            qtd_servidores = (self.servidores.count() if self.pk else 0) or 1
        # A F2 grava o total da equipe, enquanto o GV grava o valor individual.
        # Converte a representação antes de aplicar o snapshot deste ofício.
        quantidade_roteiro = roteiro.quantidade_servidores
        if not quantidade_roteiro:
            from django.core.exceptions import ValidationError
            raise ValidationError("O roteiro precisa informar o efetivo considerado no cálculo das diárias.")
        if qtd_servidores == quantidade_roteiro:
            # Mesmo efetivo do roteiro: o total já está calculado e persistido
            # pela F2. Dividir e multiplicar de volta só introduziria resto de
            # divisão — R$ 100,00 para três vira 33,333... e volta 99,999... .
            # Preserva também o "por extenso" original, que pode diferir do
            # recalculado.
            return {
                "quantidade": roteiro.resumo_diarias or "",
                "valor_decimal": roteiro.valor_diarias,
                "valor_extenso": roteiro.valor_diarias_extenso or "",
                "quantidade_servidores": qtd_servidores,
            }

        # Dinheiro é arredondado aqui, e não só na hora de imprimir: este valor
        # vai para o snapshot do artefato e é herdado por quem consome o ofício
        # depois (a prestação de contas, na F5). Sem isto, o instantâneo guarda
        # 33,33333... com 28 casas. Mesma regra do formatador de moeda.
        por_servidor = Decimal(str(roteiro.valor_diarias)) / quantidade_roteiro
        por_servidor = por_servidor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        total = por_servidor * qtd_servidores
        return {
            "quantidade": roteiro.resumo_diarias or "",
            "valor_decimal": total,
            "valor_extenso": valor_por_extenso_ptbr(total),
            "quantidade_servidores": qtd_servidores,
        }

    class Meta:
        ordering = ["-data_criacao", "-criado_em"]
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_oficio_origem"), models.UniqueConstraint(fields=["ano", "numero"],
            condition=Q(ano__isnull=False, numero__isnull=False), name=CONSTRAINT_NUMERO_OFICIO)]

    @classmethod
    def get_next_available_numero(cls, ano=None):
        from django.conf import settings
        ano = ano or timezone.localdate().year
        cfg = ConfiguracaoNumeracaoOficio.objects.filter(ano=ano).first() if getattr(settings, "OFICIO_NUMERACAO_USAR_CONFIGURACAO", True) else None
        piso = max(cfg.numero_inicial if cfg else 1, 1)
        usados = set(cls.objects.filter(ano=ano).exclude(numero__isnull=True).values_list("numero", flat=True))
        lacuna = OficioNumeroLacuna.objects.filter(ano=ano, numero__gte=piso).exclude(numero__in=usados).order_by("numero").first()
        return lacuna.numero if lacuna else max(max(usados, default=piso-1)+1, piso)

    def save(self, *args, **kwargs):
        self.protocolo = normalize_protocolo(self.protocolo)
        self.assunto = normalize_spaces(self.assunto)
        self.motivo = normalize_spaces(self.motivo)
        self.custeio_observacao = normalize_spaces(self.custeio_observacao)
        super().save(*args, **kwargs)
        if self.numero and self.ano:
            OficioNumeroLacuna.objects.filter(ano=self.ano, numero=self.numero).delete()


class ConfiguracaoNumeracaoOficio(OrigemLegado):
    ano = models.PositiveIntegerField(unique=True)
    numero_inicial = models.PositiveIntegerField(default=1)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ano"]
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_configuracaonumeracaooficio_origem")]

    def __str__(self):
        return f"{self.ano}: inicia em {self.numero_inicial}"


class OficioNumeroLacuna(OrigemLegado):
    """Somente números liberados por exclusão; saltos manuais não são lacunas."""
    ano = models.PositiveIntegerField(db_index=True)
    numero = models.PositiveIntegerField()
    liberado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ano", "numero"]
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_oficionumerolacuna_origem"), models.UniqueConstraint(fields=["ano", "numero"], name="viagens_oficio_lacuna_unica")]

    def __str__(self):
        return f"{self.numero:02d}/{self.ano}"


class ModeloMotivoOficio(ModeloTemporal, OrigemLegado):
    nome = models.CharField(max_length=120)

    texto = models.TextField()

    ativo = models.BooleanField(default=True)

    ordem = models.PositiveIntegerField(default=100)

    is_padrao = models.BooleanField(default=False)

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = normalize_upper(self.nome)
        self.texto = normalize_spaces(self.texto)
        if self.is_padrao:
            # o padrão anterior não seria desmarcado e a gravação estouraria em
            ModeloMotivoOficio.objects.exclude(pk=self.pk).update(
                is_padrao=False,
            )
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["ordem", "nome"]
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_modelomotivooficio_origem"),
            models.UniqueConstraint(fields=["nome"], name="viagens_motivo_nome_unico"),
            models.UniqueConstraint(fields=["is_padrao"], condition=Q(is_padrao=True), name="viagens_motivo_padrao_unico"),
        ]


class ModeloJustificativa(ModeloTemporal, OrigemLegado):
    """Texto reutilizável de justificativa, com padrão único global."""

    nome = models.CharField(max_length=120)

    texto = models.TextField()

    ativo = models.BooleanField(default=True)

    ordem = models.PositiveIntegerField(default=100)

    is_padrao = models.BooleanField(default=False)

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = normalize_upper(self.nome)
        self.texto = normalize_spaces(self.texto)
        if self.is_padrao:
            ModeloJustificativa.objects.exclude(pk=self.pk).update(
                is_padrao=False
            )
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["ordem", "nome"]
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_modelojustificativa_origem"),
            models.UniqueConstraint(fields=["nome"], name="viagens_justif_nome_unico"),
            models.UniqueConstraint(fields=["is_padrao"], condition=Q(is_padrao=True), name="viagens_justif_padrao_unico"),
        ]


class Justificativa(ModeloTemporal, OrigemLegado):
    STATUS_RASCUNHO = "RASCUNHO"

    STATUS_FINALIZADA = "FINALIZADA"

    STATUS_CHOICES = [
        (STATUS_RASCUNHO, "Rascunho"),
        (STATUS_FINALIZADA, "Finalizada"),
    ]

    oficio = models.OneToOneField(
        "viagens_oficios.Oficio",
        on_delete=models.CASCADE,
        related_name="justificativa",
    )

    modelo = models.ForeignKey(
        ModeloJustificativa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="justificativas",
    )

    texto = models.TextField(blank=True, default="")

    obrigatoria = models.BooleanField(default=False)

    dias_antecedencia = models.IntegerField(null=True, blank=True)

    prazo_dias = models.PositiveIntegerField(default=10)

    primeira_saida_dt = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RASCUNHO)

    def __str__(self):
        return f"Justificativa do Ofício {self.oficio.numero_formatado}"

    def save(self, *args, **kwargs):
        self.texto = normalize_spaces(self.texto)
        super().save(*args, **kwargs)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_justificativa_origem")]
