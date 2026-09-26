from core.legado import OrigemLegado
from django.contrib.auth.models import AbstractUser
from django.db import models


class Setor(models.Model):
    """Setor institucional (ex.: ASCOM). Um usuário pode ter vários setores."""

    nome = models.CharField("nome", max_length=150, unique=True)
    sigla = models.CharField("sigla", max_length=20, blank=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "setor"
        verbose_name_plural = "setores"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Modulo(models.Model):
    """Módulo funcional do sistema, liberado por setor.

    O acesso de um usuário a um módulo passa pela interseção
    usuário ↔ setores ↔ módulos; superusuários enxergam tudo.
    """

    codigo = models.CharField("código", max_length=50, unique=True)
    nome = models.CharField("nome", max_length=150)
    ativo = models.BooleanField("ativo", default=True)
    setores = models.ManyToManyField(
        Setor,
        verbose_name="setores autorizados",
        related_name="modulos",
        blank=True,
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "módulo"
        verbose_name_plural = "módulos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class User(AbstractUser, OrigemLegado):
    """Usuário do sistema.

    Modelo customizado desde o início para permitir evolução futura
    (matrícula, unidade, perfil institucional etc.) sem migração dolorosa.
    """

    # Quem cadastra digita a senha inicial e portanto a conhece; o titular
    # troca no primeiro acesso para que ela deixe de ser compartilhada.
    deve_trocar_senha = models.BooleanField(
        "precisa trocar a senha no próximo acesso", default=False
    )
    setores = models.ManyToManyField(
        Setor,
        verbose_name="setores",
        related_name="usuarios",
        blank=True,
    )
    # A pessoa do domínio de viagens que este usuário é. É o que deixa a
    # agenda dizer "onde eu estou escalado" (ofícios, termos, ordens) e não
    # só "o que eu registrei". Opcional: nem todo usuário viaja.
    servidor = models.OneToOneField(
        "viagens_cadastros.Servidor",
        verbose_name="servidor correspondente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuario",
    )

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_user_origem")]

    def __str__(self):
        return self.get_full_name() or self.username


class AssinaturaAgenda(models.Model):
    """O link pessoal de assinatura da Agenda (feed iCalendar, ver `agenda.ics`).

    O token é a única chave do feed: quem tem o link vê o que o dono do
    token vê no sistema, sem senha. Por isso ele é longo, aleatório e
    descartável — "Gerar novo link" troca o token e o anterior deixa de
    responder na hora; revogar apaga a linha.
    """

    usuario = models.OneToOneField(
        User,
        verbose_name="usuário",
        on_delete=models.CASCADE,
        related_name="assinatura_agenda",
    )
    token = models.CharField("token", max_length=64, unique=True, editable=False)
    gerado_em = models.DateTimeField("gerado em", auto_now=True)

    class Meta:
        verbose_name = "assinatura da agenda"
        verbose_name_plural = "assinaturas da agenda"

    def __str__(self):
        return f"Assinatura da agenda de {self.usuario}"

    @staticmethod
    def novo_token() -> str:
        import secrets

        return secrets.token_urlsafe(32)

    @classmethod
    def gerar(cls, usuario):
        """Cria ou troca o token da pessoa; o link antigo deixa de valer."""
        assinatura, _ = cls.objects.update_or_create(
            usuario=usuario, defaults={"token": cls.novo_token()}
        )
        return assinatura
