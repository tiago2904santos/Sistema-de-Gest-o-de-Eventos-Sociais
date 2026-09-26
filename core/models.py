from django.conf import settings
from django.db import models
from django.utils import timezone


class ModeloTemporal(models.Model):
    """Base abstrata com carimbos de criação e atualização."""

    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class ModeloCancelavel(models.Model):
    """Base abstrata para entidades canceláveis com motivo e reativação."""

    cancelado = models.BooleanField("cancelado", default=False)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)
    cancelado_em = models.DateTimeField("cancelado em", blank=True, null=True)

    class Meta:
        abstract = True

    def cancelar(self, motivo=""):
        self.cancelado = True
        self.motivo_cancelamento = motivo
        self.cancelado_em = timezone.now()
        self.save(update_fields=["cancelado", "motivo_cancelamento", "cancelado_em"])

    def reativar(self):
        self.cancelado = False
        self.motivo_cancelamento = ""
        self.cancelado_em = None
        self.save(update_fields=["cancelado", "motivo_cancelamento", "cancelado_em"])


class Notificacao(models.Model):
    """Notificação interna exibida no sino do cabeçalho."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.CASCADE,
        related_name="notificacoes",
    )
    # Sem o vínculo, apagar uma solicitação deixava a notificação apontando
    # para uma página inexistente; o cascade remove as duas juntas.
    solicitacao = models.ForeignKey(
        "solicitacoes.SolicitacaoEvento",
        verbose_name="solicitação",
        on_delete=models.CASCADE,
        related_name="notificacoes",
        blank=True,
        null=True,
    )
    titulo = models.CharField("título", max_length=150)
    mensagem = models.CharField("mensagem", max_length=255, blank=True)
    link = models.CharField("link", max_length=255, blank=True)
    lida = models.BooleanField("lida", default=False)
    criada_em = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "notificação"
        verbose_name_plural = "notificações"
        ordering = ["-criada_em"]
        indexes = [
            models.Index(fields=["usuario", "lida"]),
        ]

    def __str__(self):
        return f"{self.usuario} — {self.titulo}"


class MemoriaLeitura(models.Model):
    """O que o sistema aprendeu dos pedidos salvos a partir de um e-mail.

    Cada linha é uma contagem: quantas vezes um remetente (ou o domínio dele,
    ou uma palavra do assunto) levou a um módulo, e — com `campo` — que valor
    o formulário salvo tinha naquele campo. É daqui que a triagem da página
    inicial e o "Preencher com um e-mail" tiram as sugestões que o texto do
    e-mail não dá: "o pedido anterior desta escola foi em Ponta Grossa, com a
    professora Fulana". Ver `core.aprendizado`.
    """

    TIPO_REMETENTE = "remetente"
    TIPO_DOMINIO = "dominio"
    TIPO_PALAVRA = "palavra"
    TIPOS = (
        (TIPO_REMETENTE, "Remetente"),
        (TIPO_DOMINIO, "Domínio do remetente"),
        (TIPO_PALAVRA, "Palavra do assunto"),
    )

    tipo = models.CharField("tipo", max_length=12, choices=TIPOS)
    chave = models.CharField("chave", max_length=200)
    modulo = models.CharField("módulo", max_length=40)
    campo = models.CharField("campo", max_length=60, blank=True)
    valor = models.CharField("valor", max_length=500, blank=True)
    exibir = models.CharField("como mostrar", max_length=300, blank=True)
    vezes = models.PositiveIntegerField("vezes", default=1)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "memória de leitura"
        verbose_name_plural = "memórias de leitura"
        constraints = [
            models.UniqueConstraint(
                fields=["tipo", "chave", "modulo", "campo", "valor"], name="core_memoria_leitura_unica"
            ),
        ]
        indexes = [models.Index(fields=["tipo", "chave"])]

    def __str__(self):
        alvo = f"{self.modulo}.{self.campo}={self.exibir or self.valor}" if self.campo else self.modulo
        return f"{self.get_tipo_display()} {self.chave} → {alvo} ({self.vezes}×)"


class Feriado(models.Model):
    """Feriado estadual, municipal ou ponto facultativo local (m094).

    Os nacionais são calculados em `core.feriados` e não precisam de cadastro.
    Com `anual`, a data vale todo ano no mesmo dia e mês (o ano digitado é
    ignorado); sem, só naquela data (ponto facultativo de um ano, por exemplo).
    """

    data = models.DateField("data")
    nome = models.CharField("nome", max_length=120)
    anual = models.BooleanField("repete todo ano", default=True)

    class Meta:
        verbose_name = "feriado"
        verbose_name_plural = "feriados"
        ordering = ["data"]

    def __str__(self):
        return f"{self.data:%d/%m}{'' if self.anual else f'/{self.data:%Y}'} — {self.nome}"

    def save(self, *args, **kwargs):
        from .feriados import limpar_cache

        super().save(*args, **kwargs)
        limpar_cache()

    def delete(self, *args, **kwargs):
        from .feriados import limpar_cache

        resultado = super().delete(*args, **kwargs)
        limpar_cache()
        return resultado

