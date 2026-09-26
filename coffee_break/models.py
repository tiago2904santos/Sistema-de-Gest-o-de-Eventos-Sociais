"""Modelos do controle de Coffee Break da ASCOM.

Espelham a planilha "CONTROLE COFFE ASCOM": fornecedores contratados,
contratos, lotes (com quantitativo por exercício) e as solicitações que
consomem o saldo de cada lote. Consumido e restante são sempre calculados
a partir das solicitações — nunca armazenados.
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Coalesce
from django.utils import timezone


def normalizar_cnpj(valor):
    """Só os dígitos do CNPJ; devolve string vazia para valores vazios."""
    return re.sub(r"\D", "", valor or "")


def formatar_cnpj(digitos):
    if len(digitos) != 14:
        return digitos
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


class Fornecedor(models.Model):
    """Empresa contratada para fornecer o coffee break."""

    razao_social = models.CharField("razão social", max_length=200, unique=True)
    cnpj = models.CharField(
        "CNPJ",
        max_length=14,
        blank=True,
        help_text="Somente números; normalizado automaticamente.",
    )
    nome_curto = models.CharField(
        "nome curto", max_length=60, blank=True,
        help_text="Como aparece no detalhamento do eProtocolo, ex.: FAVO E MEL.",
    )
    contato = models.CharField("contato", max_length=150, blank=True)
    telefone = models.CharField("telefone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    url_certidao_municipal = models.URLField(
        "portal da certidão municipal", max_length=300, blank=True,
        help_text="Portal da prefeitura da sede do fornecedor (as demais certidões têm portal único).",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "fornecedor de coffee break"
        verbose_name_plural = "fornecedores de coffee break"
        ordering = ["razao_social"]
        constraints = [
            # CNPJ não se repete entre fornecedores (vazio é permitido).
            models.UniqueConstraint(
                fields=["cnpj"],
                condition=~models.Q(cnpj=""),
                name="cnpj_unico_fornecedor",
            ),
        ]

    def __str__(self):
        return self.razao_social

    @property
    def cnpj_formatado(self):
        return formatar_cnpj(self.cnpj)

    @property
    def nome_curto_efetivo(self):
        """O nome curto do cadastro, ou a razão social sem o "LTDA" do fim."""
        if self.nome_curto.strip():
            return self.nome_curto.strip().upper()
        return re.sub(r"\s+(LTDA|EIRELI|ME|EPP|S/?A)\.?$", "", self.razao_social.strip().upper())

    def clean(self):
        super().clean()
        self.cnpj = normalizar_cnpj(self.cnpj)
        if self.cnpj and len(self.cnpj) != 14:
            raise ValidationError({"cnpj": "O CNPJ deve ter 14 dígitos."})

    def save(self, *args, **kwargs):
        self.cnpj = normalizar_cnpj(self.cnpj)
        super().save(*args, **kwargs)


class ContratoCoffeeBreak(models.Model):
    """Contrato administrativo que sustenta um ou mais lotes."""

    fornecedor = models.ForeignKey(
        Fornecedor,
        verbose_name="fornecedor",
        on_delete=models.PROTECT,
        related_name="contratos",
    )
    numero = models.CharField("número do contrato", max_length=30, unique=True)
    numero_gms = models.CharField("número GMS", max_length=30, blank=True)
    termo_aditivo = models.CharField("termo aditivo", max_length=50, blank=True)
    fiscal_responsavel = models.CharField(
        "fiscal responsável", max_length=150, blank=True,
        help_text="Fiscal que atesta as notas fiscais.",
    )
    cargo_fiscal = models.CharField(
        "cargo do fiscal", max_length=100, blank=True,
        default="Agente de Polícia Judiciária",
    )
    arquivo_contrato = models.FileField(
        "contrato (PDF)", upload_to="coffee_break/contratos/", blank=True,
        help_text="Vai no pacote do protocolo de pagamento.",
    )
    arquivo_termo_aditivo = models.FileField(
        "termo aditivo (PDF)", upload_to="coffee_break/contratos/", blank=True,
        help_text="Se houver; vai no pacote logo depois do contrato.",
    )
    clausula_pagamento = models.CharField(
        "cláusula do pagamento", max_length=120, blank=True,
        default="Cláusula Décima, item 10.2.6",
        help_text="Citada no ofício que encaminha a nota para pagamento.",
    )
    objeto = models.CharField("objeto", max_length=255, blank=True)
    antecedencia_minima_dias = models.PositiveSmallIntegerField(
        "antecedência mínima do pedido (dias)", default=2,
        help_text="Pedido com menos dias até o evento aparece com aviso para ligar ao fornecedor.",
    )
    # Lidos do PDF ao anexar o contrato ou o termo aditivo (coffee_break/contratos_pdf.py).
    vigencia_inicio = models.DateField("vigência — início", null=True, blank=True)
    vigencia_fim = models.DateField(
        "vigência — fim", null=True, blank=True,
        help_text="Lida do termo aditivo; do contrato inicial, estimada pelo prazo.",
    )
    vigencia_estimada = models.BooleanField("vigência estimada", default=False)
    quantidade_contratada = models.PositiveIntegerField("quantidade contratada", null=True, blank=True)
    valor_unitario = models.DecimalField("valor unitário", max_digits=12, decimal_places=4, null=True, blank=True)
    valor_total = models.DecimalField("valor total", max_digits=14, decimal_places=2, null=True, blank=True)
    observacoes = models.TextField("observações", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "contrato de coffee break"
        verbose_name_plural = "contratos de coffee break"
        ordering = ["numero"]

    def __str__(self):
        return f"Contrato {self.numero} — {self.fornecedor}"

    @property
    def referencia_documental(self):
        """Como na OS e no certifico: "0762/2024 – GMS 7339/2024 - TERMO ADITIVO Nº 0355/2025"."""
        texto = self.numero
        if self.numero_gms:
            texto += f" – GMS {self.numero_gms}"
        if self.termo_aditivo:
            texto += f" - TERMO ADITIVO Nº {self.termo_aditivo}"
        return texto


class AditivoContrato(models.Model):
    """Cada termo aditivo do contrato, com o PDF e a vigência que ele dá.

    O contrato guarda o aditivo em vigor (o de vigência mais longa, citado nos
    documentos); aqui ficam todos, para o anexo levar os dois (ou mais) e não
    só o último.
    """

    contrato = models.ForeignKey(
        "ContratoCoffeeBreak", verbose_name="contrato", on_delete=models.CASCADE, related_name="aditivos",
    )
    numero = models.CharField("número do termo aditivo", max_length=50)
    arquivo = models.FileField("termo aditivo (PDF)", upload_to="coffee_break/contratos/", blank=True)
    vigencia_inicio = models.DateField("vigência — início", null=True, blank=True)
    vigencia_fim = models.DateField("vigência — fim", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "termo aditivo"
        verbose_name_plural = "termos aditivos"
        ordering = ["vigencia_inicio", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["contrato", "numero"], name="coffee_aditivo_unico_por_contrato"),
        ]

    def __str__(self):
        return f"Termo aditivo {self.numero}"


class ConfiguracaoCoffeeBreak(models.Model):
    """O que o ofício e o eProtocolo repetem em todo pagamento.

    Registro único (pk=1): quem assina o ofício, a quem ele vai e os campos
    fixos do cadastro do protocolo. Os valores iniciais são os do processo
    26.617.058-0.
    """

    oficio_vocativo = models.CharField(
        "vocativo do ofício", max_length=120,
        default="Excelentíssimo Senhor Delegado:",
    )
    oficio_assinante = models.CharField(
        "quem assina o ofício", max_length=150, default="JOÃO MÁRIO NUNES DE GOES",
    )
    oficio_cargo_assinante = models.CharField(
        "cargo de quem assina", max_length=150, default="Assessor de Comunicação Social",
    )
    oficio_destinatario = models.TextField(
        "destinatário do ofício",
        default=(
            "Exm° Sr. Delegado\nDr. Marcos Maurício Pestano\n"
            "Grupo Auxiliar Financeiro - GAF\nDepartamento da Polícia Civil\nCuritiba/PR"
        ),
        help_text="Uma linha por linha do bloco no pé do ofício.",
    )
    eprotocolo_assunto = models.CharField(
        "assunto no eProtocolo", max_length=80, default="LICITACAO",
    )
    eprotocolo_palavras_chave = models.CharField(
        "palavras-chave no eProtocolo", max_length=120, default="REGISTRO DE PRECO",
    )
    despacho_destino = models.CharField(
        "despacho: a quem vai", max_length=80, default="Ao GAF,",
    )
    # E-mails ao fornecedor enviados do sistema (OS e ordem bancária).
    email_copia = models.CharField(
        "e-mail da ASCOM em cópia", max_length=300, blank=True,
        help_text="Vai em cópia nos e-mails ao fornecedor. Mais de um: separe por vírgula.",
    )
    email_os_assunto = models.CharField(
        "assunto do e-mail da OS", max_length=200,
        default="Ordem de Serviço {numero} – Coffee Break – {evento}",
        help_text="Pode usar {numero}, {evento}, {data}, {horario}, {local}, {responsavel}, {quantidade} e {fornecedor}.",
    )
    email_os_texto = models.TextField(
        "texto do e-mail da OS",
        default=(
            "Prezados,\n\n"
            "Segue em anexo a Ordem de Serviço {numero}, referente ao coffee break para "
            "{quantidade} pessoas no evento \"{evento}\".\n\n"
            "Data: {data}\nHorário: {horario}\nLocal de entrega: {local}\n"
            "Responsável pelo recebimento: {responsavel}\n\n"
            "Por favor, confirmem o recebimento desta mensagem.\n\n"
            "Atenciosamente,\nAssessoria de Comunicação Social – PCPR"
        ),
        help_text="Os mesmos campos do assunto, entre chaves.",
    )
    email_ob_assunto = models.CharField(
        "assunto do e-mail da ordem bancária", max_length=200,
        default="Ordem bancária {ordem_bancaria} – pagamento da nota fiscal {nota} – Coffee Break",
        help_text="Além dos campos da OS: {nota}, {ordem_bancaria} e {data_ordem_bancaria}.",
    )
    email_ob_texto = models.TextField(
        "texto do e-mail da ordem bancária",
        default=(
            "Prezados,\n\n"
            "Informamos que foi emitida a ordem bancária {ordem_bancaria}, de {data_ordem_bancaria}, "
            "referente ao pagamento da nota fiscal {nota} (coffee break do evento \"{evento}\"). "
            "Segue o comprovante em anexo.\n\n"
            "Atenciosamente,\nAssessoria de Comunicação Social – PCPR"
        ),
    )
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "ofício e eProtocolo"
        verbose_name_plural = "ofício e eProtocolo"

    def __str__(self):
        return "Ofício de pagamento e eProtocolo"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise models.ProtectedError(
            "A configuração do ofício não se exclui; edite os campos.", [self]
        )

    @classmethod
    def atual(cls):
        return cls.objects.get_or_create(pk=1)[0]


def quantidade_efetiva(prefixo=""):
    """O que a OS desconta do lote: a quantidade faturada (a da nota), quando
    registrada; senão a pedida."""
    return Coalesce(f"{prefixo}quantidade_faturada", f"{prefixo}quantidade")


def soma_consumida(consulta):
    """Soma o consumo (quantidade efetiva) de um queryset de solicitações."""
    return consulta.aggregate(total=models.Sum(quantidade_efetiva()))["total"] or 0


class LoteQuerySet(models.QuerySet):
    def com_consumo(self):
        """Anota consumido e restante calculados das solicitações ativas."""
        consumido = Coalesce(
            models.Sum(
                quantidade_efetiva("solicitacoes__"),
                filter=models.Q(solicitacoes__cancelada=False),
            ),
            0,
        )
        return self.annotate(
            consumido=consumido,
            restante=models.F("quantidade_total") - consumido,
        )


class LoteCoffeeBreak(models.Model):
    """Lote contratado: quantitativo por exercício e municípios atendidos."""

    contrato = models.ForeignKey(
        ContratoCoffeeBreak,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="lotes",
    )
    numero = models.PositiveSmallIntegerField("número do lote")
    exercicio = models.CharField(
        "exercício", max_length=9,
        help_text="Vigência do quantitativo (ex.: 2026).",
    )
    quantidade_total = models.PositiveIntegerField(
        "quantidade total contratada", validators=[MinValueValidator(1)]
    )
    empenho = models.CharField("empenho", max_length=30, blank=True)
    valor_empenho = models.DecimalField(
        "valor do empenho", max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Quanto foi empenhado para o lote: o painel mostra o comprometido e o pago contra ele.",
    )
    municipios = models.ManyToManyField(
        "cadastros.Municipio",
        verbose_name="municípios abrangidos",
        related_name="lotes_coffee_break",
        blank=True,
    )
    municipios_texto = models.TextField(
        "municípios (texto original)", blank=True,
        help_text="Lista original da planilha, preservada integralmente.",
    )
    orientacoes = models.TextField("orientações", blank=True)
    especificacoes_tecnicas = models.TextField("especificações técnicas", blank=True)
    observacoes = models.TextField("observações", blank=True)
    ativo = models.BooleanField(
        "lote vigente", default=True,
        help_text="Só lotes vigentes recebem solicitações pelo município.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    objects = LoteQuerySet.as_manager()

    class Meta:
        verbose_name = "lote de coffee break"
        verbose_name_plural = "lotes de coffee break"
        ordering = ["-exercicio", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["contrato", "numero", "exercicio"],
                name="lote_unico_por_contrato_e_exercicio",
            ),
        ]

    def __str__(self):
        return f"Lote {self.numero} ({self.exercicio}) — {self.contrato.fornecedor}"

    @property
    def rotulo_curto(self):
        return f"Lote {self.numero} ({self.exercicio})"

    @property
    def quantidade_consumida(self):
        return soma_consumida(self.solicitacoes.filter(cancelada=False))

    @property
    def saldo_restante(self):
        return self.quantidade_total - self.quantidade_consumida

    @property
    def percentual_consumido(self):
        if not self.quantidade_total:
            return 0
        return round(self.quantidade_consumida * 100 / self.quantidade_total)


class SituacaoFinanceira(models.TextChoices):
    """Situação derivada dos marcos preenchidos — nunca gravada no banco."""

    AGUARDANDO_NOTA_FISCAL = "AGUARDANDO_NOTA_FISCAL", "Aguardando nota fiscal"
    AGUARDANDO_PROTOCOLO = "AGUARDANDO_PROTOCOLO", "Aguardando protocolo"
    AGUARDANDO_ATESTO = "AGUARDANDO_ATESTO", "Aguardando atesto"
    AGUARDANDO_ORDEM_BANCARIA = (
        "AGUARDANDO_ORDEM_BANCARIA",
        "Aguardando ordem bancária",
    )
    AGUARDANDO_ENVIO_EMPRESA = (
        "AGUARDANDO_ENVIO_EMPRESA",
        "Aguardando envio à empresa",
    )
    CONCLUIDA = "CONCLUIDA", "Concluída"
    CANCELADA = "CANCELADA", "Cancelada"


class SolicitacaoCoffeeBreak(models.Model):
    """Pedido de coffee break contra o saldo de um lote."""

    lote = models.ForeignKey(
        LoteCoffeeBreak,
        verbose_name="lote",
        on_delete=models.PROTECT,
        related_name="solicitacoes",
    )
    data_solicitacao = models.DateField(
        "data da solicitação", default=timezone.localdate
    )
    data_inicio_evento = models.DateField(
        "data de início do evento", blank=True, null=True
    )
    data_fim_evento = models.DateField("data de fim do evento", blank=True, null=True)
    periodo_evento_texto = models.CharField(
        "período do evento (texto original)", max_length=120, blank=True,
        help_text="Períodos irregulares da planilha (ex.: \"23, 24 e 25/03\").",
    )
    numero = models.CharField(
        "número da solicitação", max_length=20, blank=True,
        help_text="Identificador institucional — sempre texto (ex.: 02/2026).",
    )
    descricao_evento = models.TextField("descrição do evento")
    quantidade = models.PositiveIntegerField("quantidade solicitada")
    valor_unitario = models.DecimalField(
        "valor unitário", max_digits=12, decimal_places=4, null=True, blank=True,
        help_text="Cópia do preço do contrato na data do pedido: reajuste depois não muda o valor da OS.",
    )
    quantidade_faturada = models.PositiveIntegerField(
        "quantidade faturada", blank=True, null=True, validators=[MinValueValidator(1)],
        help_text="A da nota fiscal. Em branco, o lote desconta a quantidade pedida.",
    )
    municipio = models.ForeignKey(
        "cadastros.Municipio",
        verbose_name="município do evento",
        on_delete=models.PROTECT,
        related_name="coffee_breaks",
        blank=True,
        null=True,
        help_text="O lote é escolhido pelo município.",
    )
    horario_evento = models.TimeField("horário", blank=True, null=True)
    # De onde o pedido veio, quando foi aberto pelo "Pedir coffee break" do
    # evento (Solicitações de evento) ou da palestra (Palestras e eventos).
    solicitacao_evento = models.ForeignKey(
        "solicitacoes.SolicitacaoEvento",
        verbose_name="solicitação de evento",
        on_delete=models.SET_NULL,
        related_name="coffee_breaks",
        blank=True,
        null=True,
    )
    demanda_evento = models.ForeignKey(
        "demandas_eventos.DemandaEvento",
        verbose_name="palestra ou evento da ASCOM",
        on_delete=models.SET_NULL,
        related_name="coffee_breaks",
        blank=True,
        null=True,
    )
    detalhamento_pedido = models.TextField(
        "detalhamento do pedido", blank=True,
        help_text="Em branco, a OS monta o texto com as datas, o horário e a quantidade.",
    )
    local_entrega = models.CharField("local de entrega", max_length=255, blank=True)
    responsavel_recebimento = models.CharField(
        "responsável pelo recebimento", max_length=150, blank=True,
        help_text="Nome e telefone de quem recebe no local.",
    )
    data_envio_ordem_servico = models.DateField(
        "OS enviada ao fornecedor em", blank=True, null=True
    )
    numero_nota_fiscal = models.CharField(
        "número da nota fiscal", max_length=30, blank=True
    )
    arquivo_nota_fiscal = models.FileField(
        "nota fiscal (PDF)", upload_to="coffee_break/notas/%Y/", blank=True
    )
    # Lidos do PDF da nota ao anexar (coffee_break/nota_fiscal.py), para a
    # conferência com o fornecedor, o contrato e a data do evento.
    valor_nota_fiscal = models.DecimalField(
        "valor da nota fiscal", max_digits=12, decimal_places=2, blank=True, null=True
    )
    data_emissao_nf = models.DateField("emissão da nota fiscal", blank=True, null=True)
    cnpj_emitente_nf = models.CharField("CNPJ do emitente da nota", max_length=14, blank=True)
    numero_oficio = models.CharField(
        "número do ofício", max_length=20, blank=True,
        help_text="O ofício que encaminha a nota ao GAF (ex.: 124/2026).",
    )
    data_oficio = models.DateField("data do ofício", blank=True, null=True)
    protocolo_pcpr_oficio = models.CharField(
        "PCPR protocolo n.º", max_length=40, blank=True,
        help_text="Número que vai no alto do ofício (ex.: 2026.050880.000).",
    )
    protocolo_pagamento = models.CharField(
        "protocolo de pagamento", max_length=30, blank=True
    )
    data_atesto_gaf = models.DateField(
        "data de atesto e envio ao GAF", blank=True, null=True
    )
    data_ordem_bancaria = models.DateField(
        "ordem bancária emitida em", blank=True, null=True
    )
    data_envio_empresa = models.DateField(
        "ordem bancária enviada à empresa em", blank=True, null=True
    )
    # O comprovante da OB anexado na etapa 3 (número e valor lidos do PDF,
    # coffee_break/ordem_bancaria.py); vai por e-mail ao fornecedor.
    arquivo_ordem_bancaria = models.FileField(
        "ordem bancária (PDF)", upload_to="coffee_break/ordens_bancarias/%Y/", blank=True
    )
    numero_ordem_bancaria = models.CharField("número da ordem bancária", max_length=30, blank=True)
    valor_ordem_bancaria = models.DecimalField(
        "valor da ordem bancária", max_digits=12, decimal_places=2, blank=True, null=True
    )
    observacoes = models.TextField("observações", blank=True)

    # Cancelamento auditável: o registro permanece, fora do consumo do lote.
    cancelada = models.BooleanField("cancelada", default=False)
    cancelada_em = models.DateTimeField("cancelada em", blank=True, null=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="cancelada por",
        on_delete=models.PROTECT,
        related_name="solicitacoes_coffee_canceladas",
        blank=True,
        null=True,
    )
    motivo_cancelamento = models.CharField(
        "motivo do cancelamento", max_length=255, blank=True
    )
    # Concluída reaberta por um administrador do módulo para corrigir um dado
    # (com o motivo no histórico); volta a ser só consulta ao encerrar.
    em_correcao = models.BooleanField("reaberta para correção", default=False)

    # Pagamento conjunto: várias OS do mesmo lote num ofício e num protocolo
    # (como o 26.613.666-8, com as notas 8952 e 8954). As outras apontam para
    # a principal; o ofício, o protocolo e os marcos do pagamento são os
    # mesmos em todas (espelhados); a nota e o certifico são de cada uma.
    pagamento_com = models.ForeignKey(
        "self",
        verbose_name="pagamento junto com",
        on_delete=models.SET_NULL,
        related_name="pagamento_junto",
        blank=True,
        null=True,
    )

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criado por",
        on_delete=models.PROTECT,
        related_name="solicitacoes_coffee_criadas",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "solicitação de coffee break"
        verbose_name_plural = "solicitações de coffee break"
        ordering = ["-data_solicitacao", "-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["lote", "numero"],
                condition=~models.Q(numero=""),
                name="coffee_numero_unico_por_lote",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(data_inicio_evento__isnull=True)
                    | models.Q(data_fim_evento__isnull=True)
                    | models.Q(data_fim_evento__gte=models.F("data_inicio_evento"))
                ),
                name="coffee_periodo_evento_valido",
            ),
            # Quantidade zero só sobrevive em registro cancelado (histórico).
            models.CheckConstraint(
                condition=models.Q(quantidade__gte=1) | models.Q(cancelada=True),
                name="coffee_quantidade_positiva",
            ),
            models.CheckConstraint(
                condition=models.Q(data_ordem_bancaria__isnull=True)
                | models.Q(data_atesto_gaf__isnull=True)
                | models.Q(data_ordem_bancaria__gte=models.F("data_atesto_gaf")),
                name="coffee_ob_apos_atesto",
            ),
            models.CheckConstraint(
                condition=models.Q(data_envio_empresa__isnull=True)
                | models.Q(data_ordem_bancaria__isnull=True)
                | models.Q(data_envio_empresa__gte=models.F("data_ordem_bancaria")),
                name="coffee_envio_apos_ob",
            ),
        ]

    def __str__(self):
        rotulo = self.numero or f"#{self.pk}"
        return f"Coffee break {rotulo} — {self.lote.rotulo_curto}"

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.data_inicio_evento
            and self.data_fim_evento
            and self.data_fim_evento < self.data_inicio_evento
        ):
            errors["data_fim_evento"] = (
                "A data de fim não pode ser anterior à data de início."
            )
        if not self.cancelada and (self.quantidade or 0) < 1:
            errors["quantidade"] = "A quantidade deve ser de pelo menos 1 unidade."
        if self.protocolo_pagamento and not self.numero_nota_fiscal:
            errors["protocolo_pagamento"] = (
                "Informe a nota fiscal antes do protocolo de pagamento."
            )
        if self.data_atesto_gaf and not self.protocolo_pagamento:
            errors["data_atesto_gaf"] = (
                "Informe o protocolo de pagamento antes do atesto."
            )
        if self.data_ordem_bancaria and not self.data_atesto_gaf:
            errors["data_ordem_bancaria"] = (
                "Informe o atesto antes da ordem bancária."
            )
        if self.data_envio_empresa and not self.data_ordem_bancaria:
            errors["data_envio_empresa"] = (
                "Informe a emissão da ordem bancária antes do envio à empresa."
            )
        if (
            self.data_atesto_gaf
            and self.data_ordem_bancaria
            and self.data_ordem_bancaria < self.data_atesto_gaf
        ):
            errors["data_ordem_bancaria"] = (
                "A ordem bancária não pode ser anterior ao atesto."
            )
        if (
            self.data_ordem_bancaria
            and self.data_envio_empresa
            and self.data_envio_empresa < self.data_ordem_bancaria
        ):
            errors["data_envio_empresa"] = (
                "O envio à empresa não pode ser anterior à emissão da ordem bancária."
            )
        if errors:
            raise ValidationError(errors)

    @property
    def situacao_financeira(self):
        from . import services

        return services.situacao_financeira(self)

    @property
    def situacao_financeira_display(self):
        return SituacaoFinanceira(self.situacao_financeira).label

    @property
    def situacao_financeira_css(self):
        """Reusa as cores existentes dos status-badges do design system."""
        from . import services

        return services.CSS_SITUACAO[self.situacao_financeira]

    @property
    def periodo_evento_display(self):
        """Período legível: datas estruturadas são a fonte oficial."""
        if self.data_inicio_evento and self.data_fim_evento and (
            self.data_fim_evento != self.data_inicio_evento
        ):
            return (
                f"{self.data_inicio_evento:%d/%m/%Y} a "
                f"{self.data_fim_evento:%d/%m/%Y}"
            )
        if self.data_inicio_evento:
            return f"{self.data_inicio_evento:%d/%m/%Y}"
        return self.periodo_evento_texto

    @property
    def detalhamento_efetivo(self):
        """O pedido na OS: o texto escrito, ou "Dia 01/10 às 9h30 p/ 40 pessoas."."""
        if self.detalhamento_pedido.strip():
            return self.detalhamento_pedido.strip()
        quando = ""
        if self.data_inicio_evento:
            if self.data_fim_evento and self.data_fim_evento != self.data_inicio_evento:
                quando = f"Dias {self.data_inicio_evento:%d/%m} a {self.data_fim_evento:%d/%m}"
            else:
                quando = f"Dia {self.data_inicio_evento:%d/%m}"
        elif self.periodo_evento_texto:
            quando = f"Dia {self.periodo_evento_texto}"
        if self.horario_evento:
            hora = f"{self.horario_evento.hour}h"
            if self.horario_evento.minute:
                hora += f"{self.horario_evento.minute:02d}"
            quando = f"{quando} às {hora}".strip()
        pessoas = f"{self.quantidade} pessoas."
        return f"Solicito coffee para:\n{quando} p/ {pessoas}" if quando else f"Solicito coffee para:\n{pessoas}"

    @property
    def quantidade_efetiva(self):
        """O que desconta do lote: a faturada, quando registrada; senão a pedida."""
        return self.quantidade_faturada if self.quantidade_faturada is not None else self.quantidade

    @property
    def valor_unitario_efetivo(self):
        """O preço guardado na OS; em registro antigo sem ele, o do contrato."""
        if self.valor_unitario is not None:
            return self.valor_unitario
        return self.lote.contrato.valor_unitario if self.lote_id else None

    @property
    def valor(self):
        """Valor da OS em reais: quantidade (a faturada, se houver) × preço unitário."""
        unitario = self.valor_unitario_efetivo
        if unitario is None or self.quantidade_efetiva is None:
            return None
        from decimal import ROUND_HALF_UP, Decimal

        return (Decimal(self.quantidade_efetiva) * unitario).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def financeiro_iniciado(self):
        return any(
            (
                self.numero_nota_fiscal,
                self.protocolo_pagamento,
                self.data_atesto_gaf,
                self.data_ordem_bancaria,
                self.data_envio_empresa,
            )
        )

    @property
    def concluida(self):
        return bool(self.data_envio_empresa) and not self.cancelada

    @property
    def bloqueada_para_edicao(self):
        """Cancelada, ou concluída sem ter sido reaberta para correção."""
        return self.cancelada or (self.concluida and not self.em_correcao)

    # -- Pagamento conjunto ---------------------------------------------------

    @property
    def principal_do_pagamento(self):
        return self.pagamento_com if self.pagamento_com_id else self

    def grupo_pagamento(self):
        """As solicitações que vão no mesmo ofício e protocolo, pela ordem da
        OS (só esta, quando não há pagamento conjunto)."""
        principal = self.principal_do_pagamento
        if not principal.pk:
            return [self]
        # OS cancelada não vai no ofício nem no anexo do pagamento.
        membros = [principal, *principal.pagamento_junto.filter(cancelada=False).select_related("lote__contrato__fornecedor")]
        return sorted(membros, key=lambda s: (s.numero or "", s.pk))

    @property
    def em_pagamento_conjunto(self):
        return bool(self.pagamento_com_id) or (bool(self.pk) and self.pagamento_junto.exists())


class AcaoHistoricoCoffeeBreak(models.TextChoices):
    CRIACAO = "CRIACAO", "Solicitação criada"
    ATUALIZACAO = "ATUALIZACAO", "Solicitação atualizada"
    CANCELAMENTO = "CANCELAMENTO", "Solicitação cancelada"
    REATIVACAO = "REATIVACAO", "Solicitação reativada"
    EMAIL = "EMAIL", "E-mail enviado"
    FORNECEDOR = "FORNECEDOR", "Envio do fornecedor"


class HistoricoCoffeeBreak(models.Model):
    solicitacao = models.ForeignKey(
        SolicitacaoCoffeeBreak,
        on_delete=models.CASCADE,
        related_name="historico",
        verbose_name="solicitação",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="historico_coffee_break",
        null=True,
        blank=True,
        verbose_name="usuário",
    )
    acao = models.CharField(
        "ação", max_length=20, choices=AcaoHistoricoCoffeeBreak.choices
    )
    descricao = models.TextField("descrição", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        ordering = ["criado_em", "pk"]
        verbose_name = "histórico de coffee break"
        verbose_name_plural = "históricos de coffee break"

    def __str__(self):
        return f"{self.solicitacao_id} — {self.get_acao_display()}"


class TipoOcorrencia(models.TextChoices):
    ENTREGUE = "ENTREGUE", "Entregue sem ocorrência"
    ATRASO = "ATRASO", "Atraso na entrega"
    FALTA = "FALTA", "Falta de itens"
    QUALIDADE = "QUALIDADE", "Problema de qualidade"
    NAO_ENTREGUE = "NAO_ENTREGUE", "Não entregue"
    OUTRO = "OUTRO", "Outra ocorrência"


class OcorrenciaEntrega(models.Model):
    """A entrega do coffee break registrada depois do evento: a confirmação
    de quem recebeu, a nota de 1 a 5 e, se houve, a ocorrência (atraso, falta
    de itens, qualidade). É a base do atesto da fiscal e o histórico do
    fornecedor para notificações e sanções do contrato."""

    solicitacao = models.ForeignKey(
        SolicitacaoCoffeeBreak, verbose_name="solicitação", on_delete=models.CASCADE, related_name="ocorrencias",
    )
    tipo = models.CharField("o que aconteceu", max_length=15, choices=TipoOcorrencia.choices, default=TipoOcorrencia.ENTREGUE)
    avaliacao = models.PositiveSmallIntegerField(
        "avaliação (1 a 5)", blank=True, null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    recebido_por = models.CharField("quem recebeu", max_length=150, blank=True)
    descricao = models.TextField("observação", blank=True)
    foto = models.FileField(
        "foto ou documento", upload_to="coffee_break/ocorrencias/%Y/", blank=True,
        help_text="Opcional: PDF, PNG ou JPG.",
    )
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="registrada por", on_delete=models.SET_NULL,
        related_name="ocorrencias_coffee", blank=True, null=True,
    )
    criado_em = models.DateTimeField("registrada em", auto_now_add=True)

    class Meta:
        verbose_name = "entrega e ocorrência"
        verbose_name_plural = "entregas e ocorrências"
        ordering = ["-criado_em", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(avaliacao__isnull=True) | models.Q(avaliacao__gte=1, avaliacao__lte=5),
                name="coffee_avaliacao_1_a_5",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.solicitacao}"

    @property
    def com_problema(self):
        return self.tipo != TipoOcorrencia.ENTREGUE


class TipoCertidao(models.TextChoices):
    FEDERAL = "FEDERAL", "Federal"
    ESTADUAL = "ESTADUAL", "Estadual (Paraná)"
    MUNICIPAL = "MUNICIPAL", "Municipal"
    TRABALHISTA = "TRABALHISTA", "Trabalhista"
    FGTS = "FGTS", "FGTS"


def _certidao_upload_to(instance, filename):
    extensao = Path(filename).suffix.lower() or ".pdf"
    return (
        f"coffee_break/certidoes/{instance.fornecedor_id}/"
        f"{instance.tipo.lower()}-{instance.validade:%Y%m%d}{extensao}"
    )


class CertidaoFornecedor(models.Model):
    """Certidão de regularidade de um fornecedor.

    O histórico fica: a vigente de cada tipo é a de maior validade, e o pacote
    do protocolo de pagamento só aceita certidão vigente.
    """

    fornecedor = models.ForeignKey(
        Fornecedor,
        verbose_name="fornecedor",
        on_delete=models.CASCADE,
        related_name="certidoes",
    )
    tipo = models.CharField("tipo", max_length=12, choices=TipoCertidao.choices)
    arquivo = models.FileField("certidão (PDF)", upload_to=_certidao_upload_to)
    validade = models.DateField("válida até")
    enviada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="enviada por",
        on_delete=models.SET_NULL,
        related_name="certidoes_coffee_enviadas",
        null=True,
        blank=True,
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "certidão de fornecedor"
        verbose_name_plural = "certidões de fornecedores"
        ordering = ["fornecedor", "tipo", "-validade", "-criado_em"]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.fornecedor} (até {self.validade:%d/%m/%Y})"


# ---------------------------------------------------------------------------
# Link seguro do fornecedor (m036)
# ---------------------------------------------------------------------------

class LinkFornecedor(models.Model):
    """Link sem login que o fornecedor recebe para mandar a nota fiscal da OS
    e as certidões renovadas.

    O token é aleatório (``secrets.token_urlsafe``) e só existe no e-mail
    enviado: aqui fica o hash SHA-256. Um link ativo por solicitação — gerar
    outro revoga o anterior —, com validade (``COFFEE_LINK_FORNECEDOR_DIAS``)
    e revogável a qualquer momento. Regras em coffee_break/link_fornecedor.py.
    """

    solicitacao = models.ForeignKey(
        SolicitacaoCoffeeBreak, verbose_name="solicitação", on_delete=models.CASCADE,
        related_name="links_fornecedor",
    )
    token_hash = models.CharField("hash do token", max_length=64, unique=True, editable=False)
    expira_em = models.DateTimeField("vale até")
    revogado_em = models.DateTimeField("revogado em", blank=True, null=True)
    revogado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="revogado por", on_delete=models.SET_NULL,
        related_name="links_fornecedor_revogados", blank=True, null=True,
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="criado por", on_delete=models.SET_NULL,
        related_name="links_fornecedor_criados", blank=True, null=True,
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "link do fornecedor"
        verbose_name_plural = "links do fornecedor"
        ordering = ["-criado_em", "-pk"]

    def __str__(self):
        return f"Link do fornecedor — {self.solicitacao}"

    @property
    def expirado(self):
        return self.expira_em <= timezone.now()

    @property
    def ativo(self):
        return self.revogado_em is None and not self.expirado


class StatusEnvioFornecedor(models.TextChoices):
    RECEBIDO = "RECEBIDO", "Recebido, aguardando conferência"
    ACEITO = "ACEITO", "Conferido e aceito"
    RECUSADO = "RECUSADO", "Recusado"


TIPO_ENVIO_NOTA = "NOTA"
TIPOS_ENVIO = [(TIPO_ENVIO_NOTA, "Nota fiscal"), *[(v, f"Certidão {r}") for v, r in TipoCertidao.choices]]


class EnvioFornecedor(models.Model):
    """Um arquivo que o fornecedor mandou pelo link: fica "recebido,
    aguardando conferência" até alguém da ASCOM aceitar (aí entra na OS ou
    nas certidões do fornecedor) ou recusar."""

    link = models.ForeignKey(
        LinkFornecedor, verbose_name="link", on_delete=models.CASCADE, related_name="envios",
    )
    tipo = models.CharField("tipo", max_length=12, choices=TIPOS_ENVIO)
    arquivo = models.FileField("arquivo", upload_to="coffee_break/envios_fornecedor/%Y/")
    # Lidos do PDF da nota na chegada (a mesma leitura do anexo da etapa 2).
    numero_nota = models.CharField("número da nota", max_length=30, blank=True)
    valor_nota = models.DecimalField("valor da nota", max_digits=12, decimal_places=2, blank=True, null=True)
    emissao_nota = models.DateField("emissão da nota", blank=True, null=True)
    cnpj_nota = models.CharField("CNPJ do emitente", max_length=14, blank=True)
    validade_certidao = models.DateField("certidão válida até", blank=True, null=True)
    # O que a conferência apontou (um aviso por linha).
    avisos = models.TextField("pontos a conferir", blank=True)
    status = models.CharField(
        "situação", max_length=10, choices=StatusEnvioFornecedor.choices, default=StatusEnvioFornecedor.RECEBIDO,
    )
    conferido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="conferido por", on_delete=models.SET_NULL,
        related_name="envios_fornecedor_conferidos", blank=True, null=True,
    )
    conferido_em = models.DateTimeField("conferido em", blank=True, null=True)
    motivo_recusa = models.CharField("motivo da recusa", max_length=255, blank=True)
    criado_em = models.DateTimeField("recebido em", auto_now_add=True)

    class Meta:
        verbose_name = "envio do fornecedor"
        verbose_name_plural = "envios do fornecedor"
        ordering = ["-criado_em", "-pk"]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.link.solicitacao}"

    @property
    def eh_nota(self):
        return self.tipo == TIPO_ENVIO_NOTA

    @property
    def lista_avisos(self):
        return [linha for linha in self.avisos.splitlines() if linha.strip()]
