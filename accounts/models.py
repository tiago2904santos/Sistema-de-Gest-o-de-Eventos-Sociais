from django.contrib.auth.models import AbstractUser
from django.db import models


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

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.get_full_name() or self.username
