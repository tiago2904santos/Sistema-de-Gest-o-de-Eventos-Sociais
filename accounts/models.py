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


class User(AbstractUser):
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

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.get_full_name() or self.username
