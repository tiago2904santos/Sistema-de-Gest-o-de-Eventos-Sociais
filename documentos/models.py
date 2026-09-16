from core.legado import OrigemLegadoUUID
import uuid

from django.core.exceptions import ValidationError
from django.db import models

from django.conf import settings


class DocumentoArtefato(OrigemLegadoUUID):
    """
    Registro de documento gerado (binário, hash, snapshot) e opção de versão assinada.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tipo = models.CharField(max_length=64, db_index=True)
    formato = models.CharField(max_length=16, db_index=True)
    servidor = models.ForeignKey(
        "viagens_cadastros.Servidor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos_gerados",
    )
    oficio = models.ForeignKey("viagens_oficios.Oficio", on_delete=models.SET_NULL, null=True, blank=True, related_name="artefatos")
    prestacao = models.ForeignKey("viagens_prestacoes.PrestacaoContas", on_delete=models.SET_NULL, null=True, blank=True, related_name="artefatos")
    termo = models.ForeignKey("viagens_termos.TermoAutorizacao", on_delete=models.SET_NULL, null=True, blank=True, related_name="artefatos")
    roteiro = models.ForeignKey(
        "viagens_roteiros.Roteiro", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documentos_gerados",
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="documentos_gerados",
    )
    nome_exibicao = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Nome de exibição do arquivo, calculado na geração.",
    )
    payload_snapshot = models.JSONField(default=dict, blank=True)
    hash_sha256 = models.CharField(max_length=64)
    cache_key = models.CharField(max_length=128, db_index=True, blank=True, default="")
    generator_version = models.CharField(max_length=32, blank=True, default="")
    engine = models.CharField(max_length=32, blank=True, default="")
    arquivo = models.FileField(upload_to="documentos/gerados/%Y/%m/")
    arquivo_assinado = models.FileField(
        upload_to="documentos/assinados/%Y/%m/",
        blank=True,
        help_text="Versão assinada anexada manualmente (substitui a gerada na exibição/download).",
    )
    assinado_em = models.DateTimeField(null=True, blank=True)
    assinado_nome_original = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Nome do arquivo enviado pelo usuário, para exibição.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Artefato documental"
        verbose_name_plural = "Artefatos documentais"
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_documentoartefato_origem")]

    def __str__(self) -> str:
        return f"{self.tipo} ({self.formato}) {self.hash_sha256[:8]}"

    @property
    def esta_assinado(self) -> bool:
        if self.pk and self.versoes_assinadas.filter(revogada_em__isnull=True).exists():
            return True
        arq = self.arquivo_assinado
        if not arq or not getattr(arq, "name", ""):
            return False
        try:
            return arq.storage.exists(arq.name)
        except OSError:
            return False

    @property
    def arquivo_efetivo(self):
        """Arquivo a considerar "oficial": assinado se existir no storage, senão o gerado."""
        if self.pk:
            versao = self.versoes_assinadas.filter(
                revogada_em__isnull=True,
            ).order_by("-criado_em").first()
            if versao is not None:
                return versao.arquivo
        return self.arquivo_assinado if self.esta_assinado else self.arquivo


class DocumentoAssinaturaVersao(OrigemLegadoUUID):
    """Versão assinada append-only; revogação é tombstone, nunca exclusão."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    artefato = models.ForeignKey(
        DocumentoArtefato,
        on_delete=models.PROTECT,
        related_name="versoes_assinadas",
    )
    arquivo = models.FileField(upload_to="documentos/assinados/versoes/%Y/%m/")
    hash_sha256 = models.CharField(max_length=64, editable=False)
    nome_original = models.CharField(max_length=255, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    revogada_em = models.DateTimeField(null=True, blank=True)
    revogada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Versão assinada"
        verbose_name_plural = "Versões assinadas"
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_documentoassinaturaversao_origem")]

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            anterior = type(self).objects.get(pk=self.pk)
            campos_imutaveis = (
                "artefato_id",
                "arquivo",
                "hash_sha256",
                "nome_original",
                "criado_por_id",
            )
            if any(
                getattr(anterior, campo) != getattr(self, campo)
                for campo in campos_imutaveis
            ):
                raise ValidationError("Versões documentais assinadas são imutáveis.")
            if anterior.revogada_em and self.revogada_em != anterior.revogada_em:
                raise ValidationError("A revogação documental é imutável.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Versões documentais não podem ser excluídas.")


class DocumentoBloco(models.Model):
    """Conteúdo documental de um documento: parágrafo do modelo com override,
    ou quebra de página num ponto que o template admite.

    O que nasce de campo do ofício não passa por aqui — continua vinculado ao
    campo. Aqui fica o que é do documento e só dele: o texto reescrito de um
    parágrafo fixo (`conteudo_atual`, com o `conteudo_original` do modelo ao
    lado) e as quebras de página inseridas. Um bloco por chave e documento.
    """

    class Tipo(models.TextChoices):
        PARAGRAFO = "paragrafo", "Parágrafo"
        QUEBRA_PAGINA = "quebra_pagina", "Quebra de página"

    tipo_documento = models.CharField(max_length=64, db_index=True)
    oficio = models.ForeignKey("viagens_oficios.Oficio", on_delete=models.CASCADE, null=True, blank=True, related_name="blocos_documentais")
    termo = models.ForeignKey("viagens_termos.TermoAutorizacao", on_delete=models.CASCADE, null=True, blank=True, related_name="blocos_documentais")
    prestacao = models.ForeignKey("viagens_prestacoes.PrestacaoContas", on_delete=models.CASCADE, null=True, blank=True, related_name="blocos_documentais")
    chave = models.CharField(max_length=64)
    tipo = models.CharField(max_length=16, choices=Tipo.choices, default=Tipo.PARAGRAFO)
    ordem = models.PositiveIntegerField(default=0)
    conteudo_original = models.TextField(blank=True, default="")
    conteudo_atual = models.TextField(blank=True, default="")
    editado_manualmente = models.BooleanField(default=False)
    editado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    editado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordem", "chave"]
        verbose_name = "Bloco documental"
        verbose_name_plural = "Blocos documentais"
        constraints = [
            models.UniqueConstraint(fields=["tipo_documento", "oficio", "chave"], condition=models.Q(oficio__isnull=False), name="documentobloco_oficio_chave"),
            models.UniqueConstraint(fields=["tipo_documento", "termo", "chave"], condition=models.Q(termo__isnull=False), name="documentobloco_termo_chave"),
            models.UniqueConstraint(fields=["tipo_documento", "prestacao", "chave"], condition=models.Q(prestacao__isnull=False), name="documentobloco_prestacao_chave"),
        ]

    def __str__(self) -> str:
        return f"{self.tipo_documento}:{self.chave} ({self.get_tipo_display()})"
