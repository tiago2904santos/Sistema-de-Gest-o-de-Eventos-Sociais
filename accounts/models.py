from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Usuário do sistema.

    Modelo customizado desde o início para permitir evolução futura
    (matrícula, unidade, perfil institucional etc.) sem migração dolorosa.
    """

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.get_full_name() or self.username
