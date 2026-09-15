from core.legado import OrigemLegado
from django.db import models
from django.utils import timezone
from core.constraints import periodo_ordenado
from core.models import ModeloTemporal, ModeloCancelavel
from cadastros.models import Municipio, Estado
from viagens_cadastros.models import Servidor, Viatura
from viagens_oficios.models import Oficio

class TermoAutorizacao(ModeloTemporal, ModeloCancelavel, OrigemLegado):
    oficio = models.ForeignKey(
        Oficio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="termos_autorizacao",
        verbose_name="Oficio vinculado",
    )

    destino_estado = models.ForeignKey(
        Estado,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="UF do destino",
    )

    destino_cidade = models.ForeignKey(
        Municipio,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="termos_autorizacao",
        verbose_name="Cidade do destino",
    )

    destinos_extras = models.JSONField("Destinos adicionais", default=list, blank=True)

    data_evento_inicio = models.DateField("Data inicial do evento", null=True, blank=True)

    data_evento_fim = models.DateField("Data final do evento", null=True, blank=True)

    servidores = models.ManyToManyField(
        Servidor,
        blank=True,
        related_name="termos_autorizacao",
        verbose_name="Servidores",
    )

    viatura = models.ForeignKey(
        Viatura,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="termos_autorizacao",
        verbose_name="Viatura",
    )

    def __str__(self) -> str:
        return f"Termo #{self.pk or 'novo'} - {self.destino_display}"

    @property
    def destino_display(self) -> str:
        destino = self.destino_efetivo()
        return destino or "Destino nao informado"

    @property
    def periodo_display(self) -> str:
        inicio, fim = self.periodo_efetivo()
        if not inicio:
            return "Periodo nao informado"
        if not fim or fim == inicio:
            return inicio.strftime("%d/%m/%Y")
        return f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"

    def destino_efetivo(self) -> str:
        destinos = []
        if self.destino_cidade_id:
            destinos.append(f"{self.destino_cidade.nome}/{self.destino_cidade.estado.sigla}")
        for destino in self.destinos_extras or []:
            if not isinstance(destino, dict):
                continue
            cidade = (destino.get("cidade") or "").strip()
            uf = (destino.get("estado") or "").strip()
            if cidade and uf:
                destinos.append(f"{cidade}/{uf}")
            elif cidade or uf:
                destinos.append(cidade or uf)
        if destinos:
            return ", ".join(dict.fromkeys(destinos))
        if self.destino_estado_id:
            return self.destino_estado.sigla
        destino = self._primeiro_destino_oficio()
        # Mesmo formato do destino próprio ("Cidade/UF"): é o que a lista da origem mostra.
        return f"{destino.municipio.nome}/{destino.municipio.estado.sigla}" if destino else ""

    def periodo_efetivo(self):
        inicio = self.data_evento_inicio
        fim = self.data_evento_fim or inicio
        if inicio:
            return inicio, fim
        roteiro = getattr(self.oficio, "roteiro", None)
        if not roteiro:
            return None, None
        from viagens_oficios.roteiro_context import periodo_roteiro
        saida, retorno = periodo_roteiro(roteiro)
        inicio = timezone.localtime(saida).date() if saida else None
        fim = timezone.localtime(retorno).date() if retorno else inicio
        return inicio, fim

    def servidores_efetivos(self):
        if not self.pk:
            return Servidor.objects.none()
        # `NOVO-08`: montar um queryset novo aqui **descarta** o cache de
        # `prefetch_related("servidores")` — o related manager é clonado. O
        # resultado era a consulta do prefetch 100% desperdiçada e duas consultas
        # por linha da lista: o `.exists()` abaixo e a avaliação no presenter.
        # O prefetch da lista vem por `termos.selectors.prefetch_servidores_efetivos()`,
        # com o mesmo `select_related` e a mesma ordem desta cascata.
        if "servidores" in getattr(self, "_prefetched_objects_cache", {}):
            selecionados = self.servidores.all()
        else:
            selecionados = self.servidores.select_related("cargo", "unidade").order_by("nome")
        if selecionados.exists():
            return selecionados
        if self.oficio_id:
            do_oficio = self.oficio.servidores_termo_autorizacao.select_related("cargo", "unidade").order_by("nome")
            if do_oficio.exists():
                return do_oficio
        return Servidor.objects.none()

    def viatura_efetiva(self):
        if self.viatura_id:
            return self.viatura
        if self.oficio_id:
            return self.oficio.viatura
        return None

    def servidores_efetivos_com_oficio(self):
        """Servidores efetivos acompanhados de seu ofício, quando houver."""
        if not self.pk:
            return []
        selecionados = list(self.servidores.select_related("cargo", "unidade").order_by("nome"))
        if selecionados:
            oficio = self.oficio if self.oficio_id else None
            return [(servidor, oficio) for servidor in selecionados]
        if self.oficio_id:
            do_oficio = list(
                self.oficio.servidores_termo_autorizacao.select_related("cargo", "unidade").order_by("nome")
            )
            if do_oficio:
                return [(servidor, self.oficio) for servidor in do_oficio]
        return []

    def _primeiro_destino_oficio(self):
        roteiro = getattr(self.oficio, "roteiro", None)
        if not roteiro:
            return None
        return roteiro.destinos.select_related("municipio__estado").order_by("ordem", "pk").first()

    class Meta:
        ordering = ["-criado_em"]
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_termoautorizacao_origem"), periodo_ordenado("data_evento_inicio", "data_evento_fim", name="termo_periodo_ordenado")]
