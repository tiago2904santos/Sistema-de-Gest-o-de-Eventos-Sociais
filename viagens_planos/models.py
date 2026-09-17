"""Plano de trabalho, portado do Gerenciador de Viagens com os mesmos campos.

Os catálogos (programa solicitante, horário de atendimento, atividade e
preset de atividades) seguem a regra da casa: sem Ativo nem Ordem — apaga-se
o que não serve e a lista é alfabética. O preset mantém o padrão, que vem
escolhido na tela.

O plano de vários eventos usa o "rascunho" da origem: as seções 1 a 3
sempre editam os campos do próprio plano; "Adicionar evento ao plano" copia
esse rascunho para um `EventoPlano` e limpa os campos para o próximo.
"""

from django.db import models, transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.text import slugify

from core.constraints import nao_negativo, periodo_ordenado
from core.legado import OrigemLegado
from core.models import ModeloCancelavel, ModeloTemporal
from core.normalizers import normalize_spaces, normalize_upper

CONSTRAINT_NUMERO_PLANO_TRABALHO = "viagens_plano_trabalho_ano_numero_unique"
HORARIO_ATENDIMENTO_PADRAO = "09:00 até 17:00"


def _constraint_legado(nome):
    return models.UniqueConstraint(
        fields=["legado_origem", "legado_pk"],
        condition=models.Q(legado_pk__isnull=False),
        name=f"f6_{nome}_origem",
    )


class ProgramaSolicitante(ModeloTemporal, OrigemLegado):
    nome = models.CharField("nome", max_length=200, unique=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Programa solicitante"
        verbose_name_plural = "Programas solicitantes"
        constraints = [_constraint_legado("programasolicitante")]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = normalize_upper(self.nome)
        super().save(*args, **kwargs)


class HorarioAtendimento(ModeloTemporal, OrigemLegado):
    faixa = models.CharField("faixa", max_length=60, unique=True)  # "09:00 até 17:00"

    class Meta:
        ordering = ["faixa"]
        verbose_name = "Horário de atendimento"
        verbose_name_plural = "Horários de atendimento"
        constraints = [_constraint_legado("horarioatendimento")]

    def __str__(self):
        return self.faixa

    def save(self, *args, **kwargs):
        self.faixa = normalize_spaces(self.faixa)
        super().save(*args, **kwargs)


class AtividadePlanoTrabalho(ModeloTemporal, OrigemLegado):
    codigo = models.CharField("Código", max_length=40, unique=True)
    nome = models.CharField("Nome", max_length=255)
    meta = models.TextField("Meta")
    recurso_necessario = models.TextField("Recurso necessário", blank=True, default="")

    class Meta:
        ordering = ["nome"]
        verbose_name = "Atividade (Plano de Trabalho)"
        verbose_name_plural = "Atividades (Plano de Trabalho)"
        constraints = [_constraint_legado("atividadeplanotrabalho")]

    def __str__(self):
        return f"{self.codigo} — {self.nome}"

    @staticmethod
    def codigo_de(texto):
        return slugify(texto or "").replace("-", "_").upper()

    def save(self, *args, **kwargs):
        self.codigo = self.codigo_de(self.codigo)
        self.nome = normalize_spaces(self.nome)
        self.meta = (self.meta or "").strip()
        self.recurso_necessario = (self.recurso_necessario or "").strip()
        super().save(*args, **kwargs)


class PresetAtividadesPlanoTrabalho(ModeloTemporal, OrigemLegado):
    nome = models.CharField("Nome", max_length=200, unique=True)
    descricao = models.CharField("Descrição", max_length=255, blank=True, default="")
    is_padrao = models.BooleanField("Padrão", default=False)
    atividades = models.ManyToManyField(
        AtividadePlanoTrabalho, blank=True, related_name="presets", verbose_name="Atividades",
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "Preset de atividades"
        verbose_name_plural = "Presets de atividades"
        constraints = [
            _constraint_legado("presetatividadesplanotrabalho"),
            models.UniqueConstraint(
                fields=["is_padrao"], condition=models.Q(is_padrao=True), name="viagens_preset_padrao_unico",
            ),
        ]

    def __str__(self):
        return self.nome

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.nome = normalize_upper(self.nome)
        self.descricao = normalize_spaces(self.descricao)
        if self.is_padrao:
            type(self).objects.select_for_update().exclude(pk=self.pk).filter(is_padrao=True).update(is_padrao=False)
        super().save(*args, **kwargs)


class PlanoTrabalho(ModeloTemporal, ModeloCancelavel, OrigemLegado):
    STATUS_RASCUNHO = "RASCUNHO"
    STATUS_GERADO = "GERADO"
    STATUS_CHOICES = [(STATUS_RASCUNHO, "Rascunho"), (STATUS_GERADO, "Gerado")]

    COORDENADOR_MODO_SERVIDOR = "SERVIDOR"
    COORDENADOR_MODO_MANUAL = "MANUAL"
    COORDENADOR_MODO_CHOICES = [(COORDENADOR_MODO_SERVIDOR, "Servidor"), (COORDENADOR_MODO_MANUAL, "Manual")]

    COORDENADOR_GENERO_MASCULINO = "MASCULINO"
    COORDENADOR_GENERO_FEMININO = "FEMININO"
    COORDENADOR_GENERO_CHOICES = [(COORDENADOR_GENERO_MASCULINO, "Masculino"), (COORDENADOR_GENERO_FEMININO, "Feminino")]

    numero = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    ano = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    sufixo_numero = models.CharField(max_length=20, blank=True, default="")
    data_criacao = models.DateField(default=timezone.localdate, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RASCUNHO)
    viagem = models.ForeignKey(
        "viagens_viagem.Viagem", on_delete=models.CASCADE, null=True, blank=True,
        related_name="planos_trabalho", verbose_name="Viagem",
    )

    # Seção 1 — identificação e atuação
    contextualizacao = models.TextField("Contextualização", blank=True, default="")
    programa = models.ForeignKey(
        ProgramaSolicitante, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="planos_trabalho", verbose_name="Programa solicitante",
    )
    programa_outros = models.CharField("Programa (outros)", max_length=200, blank=True, default="")
    destino_estado = models.ForeignKey(
        "cadastros.Estado", on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name="UF do destino",
    )
    destino_cidade = models.ForeignKey(
        "cadastros.Municipio", on_delete=models.PROTECT, null=True, blank=True,
        related_name="planos_trabalho", verbose_name="Cidade do destino",
    )
    data_evento_inicio = models.DateField("Data inicial do evento", null=True, blank=True)
    data_evento_fim = models.DateField("Data final do evento", null=True, blank=True)
    horario_atendimento = models.CharField("Horário de atendimento", max_length=60, blank=True, default=HORARIO_ATENDIMENTO_PADRAO)
    coordenacao = models.TextField("Coordenador do evento", blank=True, default="")
    consideracao_final = models.TextField("Considerações finais", blank=True, default="")
    contextualizacao_auto = models.BooleanField(default=True)
    coordenacao_auto = models.BooleanField(default=True)
    consideracao_auto = models.BooleanField(default=True)
    coordenador_adm_modo = models.CharField(max_length=10, choices=COORDENADOR_MODO_CHOICES, default=COORDENADOR_MODO_SERVIDOR)
    coordenador_adm = models.ForeignKey(
        "viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="planos_trabalho_coordenador_adm", verbose_name="Coordenador administrativo",
    )
    coordenador_adm_nome_manual = models.CharField(max_length=255, blank=True, default="")
    coordenador_adm_cargo_manual = models.CharField(max_length=120, blank=True, default="")
    coordenador_adm_genero = models.CharField(max_length=10, choices=COORDENADOR_GENERO_CHOICES, blank=True, default=COORDENADOR_GENERO_MASCULINO)
    coordenador_op_modo = models.CharField(max_length=10, choices=COORDENADOR_MODO_CHOICES, default=COORDENADOR_MODO_SERVIDOR)
    coordenador_op = models.ForeignKey(
        "viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="planos_trabalho_coordenador_op", verbose_name="Coordenador operacional",
    )
    coordenador_op_nome_manual = models.CharField(max_length=255, blank=True, default="")
    coordenador_op_cargo_manual = models.CharField(max_length=120, blank=True, default="")
    coordenador_op_genero = models.CharField(max_length=10, choices=COORDENADOR_GENERO_CHOICES, blank=True, default=COORDENADOR_GENERO_MASCULINO)

    # Vários eventos
    is_multi_evento = models.BooleanField(default=False)
    evento_em_edicao = models.ForeignKey("EventoPlano", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    # Seção 2 — deslocamento e diárias
    saida_sede_data = models.DateField("Data de saída da sede", null=True, blank=True)
    saida_sede_hora = models.TimeField("Hora de saída da sede", null=True, blank=True)
    chegada_sede_data = models.DateField("Data de chegada na sede", null=True, blank=True)
    chegada_sede_hora = models.TimeField("Hora de chegada na sede", null=True, blank=True)
    diarias_composicao = models.CharField(max_length=120, blank=True, default="")
    diarias_valor_unitario = models.DecimalField("Valor por servidor", max_digits=12, decimal_places=2, null=True, blank=True)
    diarias_valor_total = models.DecimalField("Valor total do plano", max_digits=12, decimal_places=2, null=True, blank=True)
    diarias_combinada_composicao = models.CharField(max_length=120, blank=True, default="")
    diarias_combinada_valor_unitario = models.DecimalField("Valor por servidor (combinado)", max_digits=12, decimal_places=2, null=True, blank=True)
    diarias_combinada_valor_total = models.DecimalField("Valor total do plano (combinado)", max_digits=12, decimal_places=2, null=True, blank=True)

    # Seção 3 — atividades, metas e recursos (textos gerados)
    atividades_selecionadas = models.ManyToManyField(
        AtividadePlanoTrabalho, blank=True, related_name="planos", verbose_name="Atividades previstas",
    )
    metas = models.TextField(blank=True, default="")
    atividades = models.TextField(blank=True, default="")
    recursos_necessarios = models.TextField(blank=True, default="")
    unidade_movel_texto = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-ano", "-numero", "-criado_em"]
        verbose_name = "Plano de Trabalho"
        verbose_name_plural = "Planos de Trabalho"
        constraints = [
            _constraint_legado("planotrabalho"),
            models.UniqueConstraint(
                fields=["ano", "numero"],
                condition=models.Q(ano__isnull=False, numero__isnull=False),
                name=CONSTRAINT_NUMERO_PLANO_TRABALHO,
            ),
            periodo_ordenado("data_evento_inicio", "data_evento_fim", name="plano_periodo_ordenado"),
            nao_negativo("diarias_valor_unitario", name="plano_diaria_unitaria_nao_negativa"),
            nao_negativo("diarias_valor_total", name="plano_diaria_total_nao_negativa"),
            nao_negativo("diarias_combinada_valor_unitario", name="plano_diaria_comb_unitaria_nao_negativa"),
            nao_negativo("diarias_combinada_valor_total", name="plano_diaria_comb_total_nao_negativa"),
        ]

    def __str__(self):
        return f"Plano de Trabalho {self.numero_formatado}"

    @property
    def numero_formatado(self):
        if self.numero and self.ano:
            base = f"{self.numero:02d}/{self.ano}"
            return f"{base}/{self.sufixo_numero}" if self.sufixo_numero else base
        return "—"

    def destinos_rascunho(self):
        """Os destinos do rascunho (fora dos eventos já commitados), em ordem."""
        cache = getattr(self, "_prefetched_objects_cache", {}) or {}
        if "destinos" in cache:
            linhas = [d for d in self.destinos.all() if d.evento_id is None]
            return sorted(linhas, key=lambda d: (d.ordem, d.pk))
        return list(self.destinos.filter(evento__isnull=True).select_related("cidade__estado").order_by("ordem", "pk"))

    @property
    def destino_display(self):
        linhas = self.destinos_rascunho() if self.pk else []
        if linhas:
            return ", ".join(f"{d.cidade.nome}/{d.cidade.estado.sigla}" for d in linhas)
        if self.destino_cidade_id:
            return f"{self.destino_cidade.nome}/{self.destino_cidade.estado.sigla}"
        if self.destino_estado_id:
            return self.destino_estado.sigla
        return "Destino não informado"

    @property
    def periodo_display(self):
        if not self.data_evento_inicio:
            return "Período não informado"
        inicio = self.data_evento_inicio.strftime("%d/%m/%Y")
        if not self.data_evento_fim or self.data_evento_fim == self.data_evento_inicio:
            return inicio
        return f"{inicio} a {self.data_evento_fim.strftime('%d/%m/%Y')}"

    @property
    def programa_display(self):
        if self.programa_id:
            return str(self.programa)
        return self.programa_outros or ""

    @property
    def total_efetivo(self):
        cache = getattr(self, "_prefetched_objects_cache", {}) or {}
        if "efetivos" in cache:
            return sum(e.quantidade for e in self.efetivos.all())
        if not self.pk:
            return 0
        return self.efetivos.aggregate(t=models.Sum("quantidade"))["t"] or 0

    @property
    def total_efetivo_combinado(self):
        """No plano de vários eventos, a mesma equipe viaja para todos: vale o maior."""
        if not self.pk:
            return 0
        totais = [e.total_efetivo for e in self.eventos.all()]
        return max(totais) if totais else self.total_efetivo

    @property
    def eventos_ordenados(self):
        return self.eventos.order_by("ordem", "data_evento_inicio", "pk")

    def coordenador_nome_cargo(self, papel):
        assert papel in {"adm", "op"}
        servidor = getattr(self, f"coordenador_{papel}")
        if servidor is not None:
            return servidor.nome, (servidor.cargo.nome if servidor.cargo_id else "")
        return getattr(self, f"coordenador_{papel}_nome_manual"), getattr(self, f"coordenador_{papel}_cargo_manual")

    def coordenador_genero(self, papel):
        valor = (getattr(self, f"coordenador_{papel}_genero") or "").upper()
        return self.COORDENADOR_GENERO_FEMININO if valor == self.COORDENADOR_GENERO_FEMININO else self.COORDENADOR_GENERO_MASCULINO

    @property
    def tem_coordenador_operacional(self):
        return bool(self.coordenador_nome_cargo("op")[0])

    @classmethod
    def proximo_numero(cls):
        """Contador anual da configuração global, com o piso no maior número do banco."""
        from viagens_cadastros.models import ConfiguracaoSistema

        with transaction.atomic():
            config = ConfiguracaoSistema.objects.select_for_update().get(pk=ConfiguracaoSistema.get_singleton().pk)
            ano = timezone.localdate().year
            if config.pt_ano != ano:
                config.pt_ano = ano
                config.pt_ultimo_numero = 0
            piso = cls.objects.filter(ano=ano).aggregate(m=Max("numero"))["m"] or 0
            config.pt_ultimo_numero = max(config.pt_ultimo_numero, piso) + 1
            config.save(update_fields=["pt_ano", "pt_ultimo_numero", "atualizado_em"])
            return config.pt_ultimo_numero, ano, (config.pt_sufixo_numero or "").strip()

    def save(self, *args, **kwargs):
        self.programa_outros = normalize_spaces(self.programa_outros)
        self.horario_atendimento = normalize_spaces(self.horario_atendimento)
        for papel in ("adm", "op"):
            setattr(self, f"coordenador_{papel}_nome_manual", normalize_spaces(getattr(self, f"coordenador_{papel}_nome_manual")))
            setattr(self, f"coordenador_{papel}_cargo_manual", normalize_spaces(getattr(self, f"coordenador_{papel}_cargo_manual")))
            setattr(self, f"coordenador_{papel}_genero", self.coordenador_genero(papel))
        super().save(*args, **kwargs)


class PlanoDestino(ModeloTemporal, OrigemLegado):
    plano = models.ForeignKey(PlanoTrabalho, on_delete=models.CASCADE, related_name="destinos")
    # Nulo: destino do rascunho. Preenchido: cópia gravada num evento do plano.
    evento = models.ForeignKey("EventoPlano", on_delete=models.CASCADE, null=True, blank=True, related_name="destinos")
    estado = models.ForeignKey("cadastros.Estado", on_delete=models.PROTECT, related_name="+", verbose_name="UF do destino")
    cidade = models.ForeignKey("cadastros.Municipio", on_delete=models.PROTECT, related_name="planos_trabalho_destinos", verbose_name="Cidade do destino")
    ordem = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["ordem", "pk"]
        verbose_name = "Destino do plano de trabalho"
        verbose_name_plural = "Destinos do plano de trabalho"
        constraints = [
            _constraint_legado("planodestino"),
            models.UniqueConstraint(fields=["plano", "ordem"], condition=models.Q(evento__isnull=True), name="plano_destino_rascunho_ordem_unique"),
            models.UniqueConstraint(fields=["evento", "ordem"], condition=models.Q(evento__isnull=False), name="plano_destino_evento_ordem_unique"),
        ]

    def __str__(self):
        return f"{self.cidade.nome}/{self.estado.sigla}"


class EfetivoPlano(ModeloTemporal, OrigemLegado):
    plano = models.ForeignKey(PlanoTrabalho, on_delete=models.CASCADE, related_name="efetivos")
    unidade = models.ForeignKey("viagens_cadastros.Unidade", on_delete=models.PROTECT, null=True, blank=True, related_name="efetivos_plano_trabalho")
    cargo = models.ForeignKey("viagens_cadastros.Cargo", on_delete=models.PROTECT, related_name="efetivos_plano_trabalho")
    quantidade = models.PositiveIntegerField("Quantidade", default=1)

    class Meta:
        ordering = ["plano", "unidade__nome", "cargo__nome"]
        constraints = [
            _constraint_legado("efetivoplano"),
            models.UniqueConstraint(fields=["plano", "unidade", "cargo"], name="viagens_efetivo_plano_unidade_cargo_unique"),
        ]

    def __str__(self):
        return f"{self.plano_id}: {self.quantidade} x {self.cargo} / {self.unidade}"


class EventoPlano(ModeloTemporal, OrigemLegado):
    """Um evento gravado de um plano de vários eventos (cópia do rascunho)."""

    plano = models.ForeignKey(PlanoTrabalho, on_delete=models.CASCADE, related_name="eventos")
    ordem = models.PositiveIntegerField(default=1)
    programa = models.ForeignKey(ProgramaSolicitante, on_delete=models.SET_NULL, null=True, blank=True, related_name="eventos_plano_trabalho")
    programa_outros = models.CharField("Programa (outros)", max_length=200, blank=True, default="")
    data_evento_inicio = models.DateField("Data inicial do evento", null=True, blank=True)
    data_evento_fim = models.DateField("Data final do evento", null=True, blank=True)
    horario_atendimento = models.CharField("Horário de atendimento", max_length=60, blank=True, default=HORARIO_ATENDIMENTO_PADRAO)
    # Só o coordenador operacional varia por evento; o administrativo é do plano.
    coordenador_op_modo = models.CharField(max_length=10, choices=PlanoTrabalho.COORDENADOR_MODO_CHOICES, default=PlanoTrabalho.COORDENADOR_MODO_SERVIDOR)
    coordenador_op = models.ForeignKey("viagens_cadastros.Servidor", on_delete=models.SET_NULL, null=True, blank=True, related_name="eventos_plano_coordenador_op")
    coordenador_op_nome_manual = models.CharField(max_length=255, blank=True, default="")
    coordenador_op_cargo_manual = models.CharField(max_length=120, blank=True, default="")
    coordenador_op_genero = models.CharField(max_length=10, choices=PlanoTrabalho.COORDENADOR_GENERO_CHOICES, blank=True, default=PlanoTrabalho.COORDENADOR_GENERO_MASCULINO)
    atividades_selecionadas = models.ManyToManyField(AtividadePlanoTrabalho, blank=True, related_name="eventos")
    metas = models.TextField(blank=True, default="")
    atividades_texto = models.TextField(blank=True, default="")
    recursos_necessarios = models.TextField(blank=True, default="")
    unidade_movel_texto = models.TextField(blank=True, default="")
    diarias_composicao = models.CharField(max_length=120, blank=True, default="")
    diarias_valor_unitario = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    diarias_valor_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["ordem", "data_evento_inicio", "pk"]
        constraints = [
            _constraint_legado("eventoplano"),
            periodo_ordenado("data_evento_inicio", "data_evento_fim", name="evento_plano_periodo_ordenado"),
            nao_negativo("diarias_valor_unitario", name="evento_plano_diaria_unitaria_nao_negativa"),
            nao_negativo("diarias_valor_total", name="evento_plano_diaria_total_nao_negativa"),
            models.UniqueConstraint(fields=["plano", "ordem"], name="evento_plano_ordem_unique"),
        ]

    def __str__(self):
        return f"Evento {self.ordem} do plano {self.plano_id}"

    @property
    def total_efetivo(self):
        cache = getattr(self, "_prefetched_objects_cache", {}) or {}
        if "efetivos" in cache:
            return sum(e.quantidade for e in self.efetivos.all())
        return self.efetivos.aggregate(t=models.Sum("quantidade"))["t"] or 0

    @property
    def destino_principal(self):
        return self.destinos.select_related("cidade__estado").order_by("ordem", "pk").first()

    @property
    def periodo_display(self):
        if not self.data_evento_inicio:
            return "Período não informado"
        inicio = self.data_evento_inicio.strftime("%d/%m/%Y")
        if not self.data_evento_fim or self.data_evento_fim == self.data_evento_inicio:
            return inicio
        return f"{inicio} a {self.data_evento_fim.strftime('%d/%m/%Y')}"

    @property
    def programa_display(self):
        return str(self.programa) if self.programa_id else (self.programa_outros or "")

    @property
    def destino_display(self):
        destinos = list(self.destinos.select_related("cidade__estado").order_by("ordem", "pk"))
        if not destinos:
            return "Destino não informado"
        return ", ".join(f"{d.cidade.nome}/{d.cidade.estado.sigla}" for d in destinos)

    def coordenador_nome_cargo(self):
        if self.coordenador_op_id:
            return self.coordenador_op.nome, (self.coordenador_op.cargo.nome if self.coordenador_op.cargo_id else "")
        return self.coordenador_op_nome_manual, self.coordenador_op_cargo_manual

    def coordenador_genero(self):
        valor = (self.coordenador_op_genero or "").upper()
        return PlanoTrabalho.COORDENADOR_GENERO_FEMININO if valor == PlanoTrabalho.COORDENADOR_GENERO_FEMININO else PlanoTrabalho.COORDENADOR_GENERO_MASCULINO

    def save(self, *args, **kwargs):
        self.programa_outros = normalize_spaces(self.programa_outros)
        self.horario_atendimento = normalize_spaces(self.horario_atendimento)
        self.coordenador_op_nome_manual = normalize_spaces(self.coordenador_op_nome_manual)
        self.coordenador_op_cargo_manual = normalize_spaces(self.coordenador_op_cargo_manual)
        self.coordenador_op_genero = self.coordenador_genero()
        super().save(*args, **kwargs)


class EfetivoEvento(ModeloTemporal, OrigemLegado):
    evento = models.ForeignKey(EventoPlano, on_delete=models.CASCADE, related_name="efetivos")
    unidade = models.ForeignKey("viagens_cadastros.Unidade", on_delete=models.PROTECT, null=True, blank=True, related_name="efetivos_evento_plano_trabalho")
    cargo = models.ForeignKey("viagens_cadastros.Cargo", on_delete=models.PROTECT, related_name="efetivos_evento_plano_trabalho")
    quantidade = models.PositiveIntegerField("Quantidade", default=1)

    class Meta:
        ordering = ["evento", "unidade__nome", "cargo__nome"]
        constraints = [
            _constraint_legado("efetivoevento"),
            models.UniqueConstraint(fields=["evento", "unidade", "cargo"], name="viagens_efetivo_evento_unidade_cargo_unique"),
        ]

    def __str__(self):
        return f"{self.evento_id}: {self.quantidade} x {self.cargo} / {self.unidade}"
