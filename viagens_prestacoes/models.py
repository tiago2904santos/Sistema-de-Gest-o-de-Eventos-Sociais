from django.db import models
from .arquivos import ArquivoPrivadoField
from core.constraints import periodo_ordenado
from core.constraints import positivo
from django.db.models import Q
from django.core.validators import FileExtensionValidator
from viagens_cadastros.models import Servidor
from viagens_cadastros.models import Viatura
from viagens_oficios.models import Oficio
from viagens_roteiros.models import RoteiroTrecho
from core.uploads import validate_private_document_upload
PRESTACAO_DOCUMENTO_EXTENSOES = ['pdf', 'png', 'jpg', 'jpeg']

def prestacao_documento_upload_to(instance, filename):
    return f"viagens_prestacoes/{instance.pk or 'nova'}/{filename}"

def prestacao_documento_anexo_upload_to(instance, filename):
    return f"viagens_prestacoes/{instance.prestacao_id or 'nova'}/{filename}"

def prestacao_anexo_original_upload_to(instance, filename):
    """O PDF como veio do eProtocolo, antes de receber os números.

    Fica separado do carimbado porque é dele que todo recarimbo parte: sem o cru,
    ajustar a posição desenharia por cima de um arquivo que já tem os números.
    """
    return f"viagens_prestacoes/{instance.prestacao_id or 'nova'}/originais/{filename}"

class PrestacaoContas(models.Model):
    STATUS_PENDENTE = 'pendente'
    STATUS_EM_PREENCHIMENTO = 'em_preenchimento'
    STATUS_ENVIADA = 'enviada'
    STATUS_APROVADA = 'aprovada'
    STATUS_REPROVADA = 'reprovada'
    STATUS_CHOICES = [(STATUS_PENDENTE, 'Pendente'), (STATUS_EM_PREENCHIMENTO, 'Em preenchimento'), (STATUS_ENVIADA, 'Enviada'), (STATUS_APROVADA, 'Aprovada'), (STATUS_REPROVADA, 'Reprovada')]
    oficio = models.OneToOneField(Oficio, on_delete=models.CASCADE, related_name='prestacao_contas')
    roteiro_ajustado = models.ForeignKey('viagens_roteiros.Roteiro', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    despacho_assinado = ArquivoPrivadoField('Despacho assinado do ofício', upload_to=prestacao_documento_upload_to, blank=True, validators=[FileExtensionValidator(PRESTACAO_DOCUMENTO_EXTENSOES)])
    observacoes = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Prestação de Contas'
        verbose_name_plural = 'Prestações de Contas'

    def __str__(self):
        return f'Prestação — Ofício {self.oficio.numero_formatado}'

class PrestacaoServidorAtivosManager(models.Manager):
    """Manager padrão de registros ativos; ``todos`` inclui remoções reversíveis."""

    def get_queryset(self):
        return super().get_queryset().filter(removida_em__isnull=True)

class PrestacaoServidor(models.Model):
    """Parte individual da prestação de um servidor dentro do ofício.

    Guarda o acompanhamento e o que muda de servidor para servidor: status,
    arquivamento/finalização, número da solicitação, comprovante de saque/
    transferência (via ``PrestacaoDocumentoAnexo``) e a assinatura do relatório
    técnico (via ``AssinaturaDocumento``). O texto do RT e o diário de bordo são
    compartilhados e ficam em ``PrestacaoContas``.
    """
    STATUS_PENDENTE = PrestacaoContas.STATUS_PENDENTE
    STATUS_EM_PREENCHIMENTO = PrestacaoContas.STATUS_EM_PREENCHIMENTO
    STATUS_ENVIADA = PrestacaoContas.STATUS_ENVIADA
    STATUS_APROVADA = PrestacaoContas.STATUS_APROVADA
    STATUS_REPROVADA = PrestacaoContas.STATUS_REPROVADA
    STATUS_CHOICES = PrestacaoContas.STATUS_CHOICES
    prestacao = models.ForeignKey(PrestacaoContas, on_delete=models.CASCADE, related_name='servidores_prestacao')
    servidor = models.ForeignKey(Servidor, on_delete=models.CASCADE, related_name='prestacoes_servidor')
    numero_solicitacao = models.CharField('Número da solicitação', max_length=60, blank=True, default='')
    diaria_valor_override = models.DecimalField('Diária recebida por este servidor', max_digits=10, decimal_places=2, null=True, blank=True)
    diaria_valor_override_observacao = models.CharField('Observação sobre o valor recebido', max_length=255, blank=True, default='')
    data_liberacao_diarias = models.DateField('Data de liberação das diárias', null=True, blank=True)
    prazo_limite_saque = models.DateField('Prazo limite para saque', null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    arquivada = models.BooleanField(default=False)
    arquivada_em = models.DateTimeField(null=True, blank=True)
    finalizada = models.BooleanField(default=False)
    finalizada_em = models.DateTimeField(null=True, blank=True)
    removida_em = models.DateTimeField('Removida da equipe em', null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    objects = PrestacaoServidorAtivosManager()
    todos = models.Manager()

    class Meta:
        default_manager_name = 'objects'
        ordering = ['prestacao', 'pk']
        verbose_name = 'Servidor da prestação'
        verbose_name_plural = 'Servidores da prestação'
        indexes = [models.Index(fields=['arquivada', 'finalizada', 'data_liberacao_diarias'], name='prest_serv_aba_idx'), models.Index(fields=['status'], name='prest_serv_status_idx')]
        constraints = [models.UniqueConstraint(fields=['prestacao', 'servidor'], name='unique_servidor_por_prestacao'), positivo('diaria_valor_override', name='prest_serv_diaria_recebida_positiva'), periodo_ordenado('data_liberacao_diarias', 'prazo_limite_saque', name='prest_serv_prazo_apos_liberacao')]

    def __str__(self):
        return f'{self.servidor} — Ofício {self.prestacao.oficio.numero_formatado}'

    @property
    def oficio(self):
        return self.prestacao.oficio

    @property
    def is_motorista(self) -> bool:
        return bool(self.prestacao.oficio.motorista_id and self.servidor_id == self.prestacao.oficio.motorista_id)

    @property
    def status_display(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def status_variant(self):
        return {self.STATUS_PENDENTE: 'pending', self.STATUS_EM_PREENCHIMENTO: 'warning', self.STATUS_ENVIADA: 'info', self.STATUS_APROVADA: 'success', self.STATUS_REPROVADA: 'danger'}.get(self.status, 'muted')

    def definir_arquivada(self, arquivada: bool):
        """Arquiva/desarquiva este servidor, registrando o momento do arquivamento."""
        from django.utils import timezone as _tz
        self.arquivada = arquivada
        self.arquivada_em = _tz.now() if arquivada else None
        self.save(update_fields=['arquivada', 'arquivada_em', 'atualizado_em'])

    def definir_finalizada(self, finalizada: bool):
        """Conclui/reabre a prestação deste servidor, registrando o momento."""
        from django.utils import timezone as _tz
        self.finalizada = finalizada
        self.finalizada_em = _tz.now() if finalizada else None
        self.save(update_fields=['finalizada', 'finalizada_em', 'atualizado_em'])

    def marcar_em_preenchimento(self):
        if self.status == self.STATUS_PENDENTE:
            self.status = self.STATUS_EM_PREENCHIMENTO
            self.save(update_fields=['status', 'atualizado_em'])

    def tem_dados_coletados(self) -> bool:
        """Há trabalho de usuário nesta linha que uma exclusão destruiria (`DB-06`).

        A lista é exaustiva contra os campos editáveis do modelo, e
        `CamposConhecidosDoServidorDaPrestacaoTests` reprova quando aparece um
        campo novo — é a única forma de um campo futuro não voltar a ser apagado
        em silêncio pela troca de equipe.
        """
        return bool(self.numero_solicitacao.strip() or self.diaria_valor_override is not None or self.diaria_valor_override_observacao.strip() or self.data_liberacao_diarias or self.prazo_limite_saque or (self.status != self.STATUS_PENDENTE) or self.arquivada or self.finalizada or self.documentos_anexos.exists() or (hasattr(self, 'assinaturas') and self.assinaturas.exists()))

    def tem_prova_irrefazivel(self) -> bool:
        """Só o que ninguém consegue refazer se a linha sumir (`NOVO-35`).

        Predicado deliberadamente MAIS ESTREITO que `tem_dados_coletados()`, e a
        diferença é de propósito: preservar uma linha e **bloquear um cadastro
        inteiro** são decisões de peso diferente. Dado barato justifica não
        apagar; não justifica prender.

        O que ficou de fora, e por quê: `status`, `arquivada`, `finalizada`,
        `data_liberacao_diarias`, `prazo_limite_saque` e os campos de override são
        estado de fluxo, refazíveis em segundos. Pior, `status` é **coletivo**:
        `services.marcar_servidores_pendentes` marca toda a equipe pendente do
        ofício ao salvar um documento COMPARTILHADO (despacho, RT, diário). Medido:
        basta alguém salvar o despacho para que um servidor semeado por engano
        passe a "ter dados coletados" sem nunca ter entregue nada — e ficaria
        indelével para sempre por ação de terceiro.

        Aqui ficam os três que, apagados, não voltam: o arquivo do comprovante, a
        assinatura eletrônica e o número da solicitação digitado à mão.
        """
        return bool(self.documentos_anexos.exists() or (hasattr(self, 'assinaturas') and self.assinaturas.exists()) or self.numero_solicitacao.strip())

    def sair_da_equipe(self) -> bool:
        """Tira este servidor da equipe corrente. Devolve `True` se preservou a linha.

        Sem nada coletado não há o que preservar, e a linha some de vez — que é o
        comportamento de sempre e o que impede a prestação de exibir servidores
        semeados pelo wizard e depois retirados. Com dados, a linha fica marcada.
        """
        from django.utils import timezone as _tz
        if not self.tem_dados_coletados():
            self.delete()
            return False
        if self.removida_em is None:
            self.removida_em = _tz.now()
            self.save(update_fields=['removida_em', 'atualizado_em'])
        return True

    def voltar_para_equipe(self) -> None:
        """Desfaz `sair_da_equipe`, e com ela reaparecem anexos e assinaturas."""
        if self.removida_em is None:
            return
        self.removida_em = None
        self.save(update_fields=['removida_em', 'atualizado_em'])

class PrestacaoDocumentoAnexo(models.Model):
    TIPO_DESPACHO = 'despacho'
    TIPO_OFICIO_ASSINADO = 'oficio_assinado'
    TIPO_COMPROVANTE = 'comprovante'
    TIPO_RT_ASSINADO = 'rt_assinado'
    TIPO_DB_ASSINADO = 'db_assinado'
    TIPO_CHOICES = [(TIPO_DESPACHO, 'Despacho assinado do ofício'), (TIPO_OFICIO_ASSINADO, 'Ofício assinado'), (TIPO_COMPROVANTE, 'Comprovante de saque/transferência'), (TIPO_RT_ASSINADO, 'Relatório técnico assinado'), (TIPO_DB_ASSINADO, 'Diário de bordo assinado')]
    prestacao = models.ForeignKey(PrestacaoContas, on_delete=models.CASCADE, related_name='documentos_anexos')
    servidor_prestacao = models.ForeignKey(PrestacaoServidor, on_delete=models.CASCADE, null=True, blank=True, related_name='documentos_anexos')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    arquivo = ArquivoPrivadoField(upload_to=prestacao_documento_anexo_upload_to, validators=[validate_private_document_upload])
    arquivo_original = ArquivoPrivadoField(upload_to=prestacao_anexo_original_upload_to, blank=True, help_text='PDF como enviado, antes do carimbo. Origem de todo recarimbo.')
    nome_original = models.CharField(max_length=255, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    @property
    def arquivo_para_carimbar(self):
        """De onde o carimbo parte: o cru quando existe, senão o próprio arquivo.

        O `or` cobre os anexos criados antes deste campo — carimbá-los uma vez é
        correto; o segundo carimbo é que duplicaria, e a partir da primeira vez o cru
        passa a existir.
        """
        return self.arquivo_original if self.arquivo_original else self.arquivo

    class Meta:
        ordering = ['tipo', 'criado_em', 'pk']
        verbose_name = 'Anexo da prestação de contas'
        verbose_name_plural = 'Anexos da prestação de contas'

    def __str__(self):
        return self.nome_original or self.arquivo.name

class CarimboSolicitacao(models.Model):
    """Onde o número de solicitação de um servidor é desenhado no ofício assinado.

    O ofício que volta do eProtocolo traz a coluna de solicitação em branco — o número
    só existe depois de protocolar. Esta linha guarda o LUGAR do carimbo; o texto é
    sempre `PrestacaoServidor.numero_solicitacao`, lido na hora de desenhar. Uma fonte
    só: corrigir o número no cadastro refaz o carimbo sem ninguém sincronizar nada.

    As coordenadas seguem a convenção do navegador e de
    `documentos.services.pdf_overlay`: frações da página, origem no topo-esquerdo.
    """
    anexo = models.ForeignKey(PrestacaoDocumentoAnexo, on_delete=models.CASCADE, related_name='carimbos')
    servidor_prestacao = models.ForeignKey(PrestacaoServidor, on_delete=models.CASCADE, related_name='carimbos_solicitacao')
    pagina = models.PositiveSmallIntegerField(default=0)
    x = models.FloatField(help_text='Fração da largura, 0 = borda esquerda.')
    y = models.FloatField(help_text='Fração da altura, 0 = topo da página.')
    tamanho = models.FloatField(default=0.012)
    ajustado_manualmente = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['anexo', 'servidor_prestacao'], name='carimbo_unico_por_servidor_no_anexo')]
        ordering = ['pagina', 'y', 'x', 'pk']
        verbose_name = 'Carimbo do número de solicitação'
        verbose_name_plural = 'Carimbos do número de solicitação'

    def __str__(self):
        return f'carimbo p{self.pagina} de {self.servidor_prestacao_id}'

class RelatorioTecnico(models.Model):
    prestacao = models.OneToOneField(PrestacaoContas, on_delete=models.CASCADE, related_name='relatorio_tecnico')
    motivo = models.TextField(blank=True, default='')
    diaria = models.CharField(max_length=255, blank=True, default='')
    translado = models.CharField(max_length=255, blank=True, default='')
    combustivel = models.CharField(max_length=255, blank=True, default='')
    passagem = models.CharField(max_length=255, blank=True, default='')
    atividade = models.TextField(blank=True, default='')
    conclusao = models.TextField(blank=True, default='')
    medidas = models.TextField(blank=True, default='')
    info_complementares = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Relatório Técnico'
        verbose_name_plural = 'Relatórios Técnicos'

    def __str__(self):
        return f'RT — {self.prestacao}'

class DiarioBordo(models.Model):
    """Diário de bordo do veículo gerado a partir do roteiro do ofício da prestação.

    Os dados de cabeçalho (motorista, viatura, ofício, e-protocolo) vêm do ofício;
    os trechos vêm do roteiro. O usuário complementa KM inicial/final e a
    necessidade de abastecimento de cada trecho (ver ``DiarioBordoTrecho``).
    """
    MOTORISTA_MODO_OFICIO = 'OFICIO'
    MOTORISTA_MODO_SERVIDOR = 'SERVIDOR'
    MOTORISTA_MODO_OUTRO = 'OUTRO_OFICIO'
    MOTORISTA_MODO_CHOICES = [(MOTORISTA_MODO_OFICIO, 'Manter motorista do ofício'), (MOTORISTA_MODO_SERVIDOR, 'Outro servidor deste ofício'), (MOTORISTA_MODO_OUTRO, 'Motorista de outro ofício')]
    VIATURA_MODO_OFICIO = 'OFICIO'
    VIATURA_MODO_BANCO = 'BANCO'
    VIATURA_MODO_MANUAL = 'MANUAL'
    VIATURA_MODO_CHOICES = [(VIATURA_MODO_OFICIO, 'Manter a viatura do ofício'), (VIATURA_MODO_BANCO, 'Selecionar do cadastro'), (VIATURA_MODO_MANUAL, 'Preencher manualmente')]
    prestacao = models.OneToOneField(PrestacaoContas, on_delete=models.CASCADE, related_name='diario_bordo')
    motorista_modo = models.CharField(max_length=16, choices=MOTORISTA_MODO_CHOICES, default=MOTORISTA_MODO_OFICIO)
    motorista_servidor = models.ForeignKey(Servidor, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name='Motorista (servidor do ofício)')
    motorista_manual_nome = models.CharField(max_length=255, blank=True, default='')
    motorista_manual_cpf = models.CharField(max_length=11, blank=True, default='')
    motorista_oficio_referencia = models.CharField(max_length=16, blank=True, default='', verbose_name='Ofício do motorista', help_text='Referência no formato número/ano (ex.: 15/2026).')
    motorista_protocolo_ref = models.CharField(max_length=30, blank=True, default='', verbose_name='Protocolo do motorista')
    viatura_modo = models.CharField(max_length=10, choices=VIATURA_MODO_CHOICES, default=VIATURA_MODO_OFICIO)
    viatura = models.ForeignKey('viagens_cadastros.Viatura', on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name='Viatura (cadastro)')
    viatura_manual_modelo = models.CharField(max_length=120, blank=True, default='')
    viatura_manual_placa = models.CharField(max_length=8, blank=True, default='')
    viatura_manual_tipo = models.CharField(max_length=20, choices=Viatura.Tipo.choices, blank=True, default='')
    viatura_manual_combustivel = models.CharField(max_length=60, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Diário de Bordo'
        verbose_name_plural = 'Diários de Bordo'

    def __str__(self):
        return f'Diário de bordo — {self.prestacao}'

    @property
    def motorista_alterado(self) -> bool:
        """True quando o motorista foi trocado em relação ao do ofício."""
        return self.motorista_modo != self.MOTORISTA_MODO_OFICIO

    @property
    def viatura_alterada(self) -> bool:
        """True quando a viatura foi trocada em relação à do ofício."""
        return self.viatura_modo != self.VIATURA_MODO_OFICIO

class DiarioBordoTrecho(models.Model):
    """Linha do diário de bordo, espelhando um trecho do roteiro do ofício."""
    diario = models.ForeignKey(DiarioBordo, on_delete=models.CASCADE, related_name='trechos')
    trecho = models.ForeignKey(RoteiroTrecho, on_delete=models.SET_NULL, null=True, blank=True, related_name='diario_bordo_trechos')
    ordem = models.PositiveIntegerField(default=0)
    km_inicial = models.PositiveIntegerField(null=True, blank=True)
    km_final = models.PositiveIntegerField(null=True, blank=True)
    abastecimento = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ['diario', 'ordem', 'pk']
        verbose_name = 'Trecho do diário de bordo'
        verbose_name_plural = 'Trechos do diário de bordo'
        constraints = [models.UniqueConstraint(fields=['diario', 'ordem'], name='diario_trecho_ordem_unique'), periodo_ordenado('km_inicial', 'km_final', name='diario_trecho_km_ordenado', mensagem='O km final não pode ser menor que o km inicial.')]

    def __str__(self):
        return f'Trecho {self.ordem} — {self.diario_id}'

class ModeloTextoRelatorioTecnico(models.Model):
    """Textos reutilizáveis para preencher rapidamente os campos do RT."""
    CAMPO_MOTIVO = 'motivo'
    CAMPO_ATIVIDADE = 'atividade'
    CAMPO_CONCLUSAO = 'conclusao'
    CAMPO_MEDIDAS = 'medidas'
    CAMPO_INFO = 'info_complementares'
    CAMPO_CHOICES = [(CAMPO_MOTIVO, 'Descrição do evento'), (CAMPO_ATIVIDADE, 'Objetivo da participação'), (CAMPO_CONCLUSAO, 'Conclusão'), (CAMPO_MEDIDAS, 'Medidas a serem adotadas pelo órgão'), (CAMPO_INFO, 'Informações complementares')]
    campo = models.CharField(max_length=30, choices=CAMPO_CHOICES, db_index=True)
    nome = models.CharField(max_length=120)
    texto = models.TextField()
    ordem = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ['campo', 'ordem', 'nome']
        verbose_name = 'Modelo de texto do RT'
        verbose_name_plural = 'Modelos de texto do RT'
        constraints = [models.UniqueConstraint(fields=['campo', 'nome'], name='unique_modelo_texto_rt_campo_nome')]

    def __str__(self):
        return f'{self.get_campo_display()} — {self.nome}'


def assinatura_origem_upload_to(instance, filename):
    return f"viagens_prestacoes/{instance.prestacao_id or 'nova'}/assinaturas/origem_{instance.tipo}_{filename}"

def assinatura_png_upload_to(instance, filename):
    return f"viagens_prestacoes/{instance.prestacao_id or 'nova'}/assinaturas/png_{instance.tipo}_{filename}"

def assinatura_assinado_upload_to(instance, filename):
    return f"viagens_prestacoes/{instance.prestacao_id or 'nova'}/assinaturas/assinado_{instance.tipo}_{filename}"

class AssinaturaDocumento(models.Model):
    """Assinatura por link público: apenas SHA-256 do token é persistido.

    Cada emissão tem snapshot imutável. Revogações preservam a prova anterior;
    somente um registro vigente existe por documento e signatário.
    """
    TIPO_RT = 'rt'
    TIPO_DB = 'db'
    TIPO_CHOICES = [(TIPO_RT, 'Relatório Técnico'), (TIPO_DB, 'Diário de Bordo')]
    STATUS_PENDENTE = 'pendente'
    STATUS_ASSINADA = 'assinada'
    STATUS_CANCELADA = 'cancelada'
    STATUS_CHOICES = [(STATUS_PENDENTE, 'Pendente'), (STATUS_ASSINADA, 'Assinada'), (STATUS_CANCELADA, 'Cancelada')]
    MODO_FONTE = 'fonte'
    MODO_DESENHO = 'desenho'
    MODO_CHOICES = [(MODO_FONTE, 'Fonte'), (MODO_DESENHO, 'Desenho')]
    prestacao = models.ForeignKey(PrestacaoContas, on_delete=models.CASCADE, related_name='assinaturas')
    servidor_prestacao = models.ForeignKey(PrestacaoServidor, on_delete=models.CASCADE, null=True, blank=True, related_name='assinaturas')
    tipo = models.CharField(max_length=4, choices=TIPO_CHOICES, db_index=True)
    signer = models.ForeignKey(Servidor, on_delete=models.PROTECT, related_name='assinaturas_documentos')
    nome_esperado = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    link_token_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)
    link_criado_em = models.DateTimeField(null=True, blank=True)
    link_expira_em = models.DateTimeField(null=True, blank=True)
    identidade_confirmada_em = models.DateTimeField(null=True, blank=True)
    arquivo_origem = ArquivoPrivadoField(upload_to=assinatura_origem_upload_to, blank=True)
    modo = models.CharField(max_length=10, choices=MODO_CHOICES, blank=True, default='')
    fonte = models.CharField(max_length=60, blank=True, default='')
    assinatura_png = ArquivoPrivadoField(upload_to=assinatura_png_upload_to, blank=True)
    pagina = models.PositiveIntegerField(default=0)
    pos_x = models.FloatField(null=True, blank=True)
    pos_y = models.FloatField(null=True, blank=True)
    largura = models.FloatField(null=True, blank=True)
    altura = models.FloatField(null=True, blank=True)
    arquivo_assinado = ArquivoPrivadoField(upload_to=assinatura_assinado_upload_to, blank=True)
    assinado_em = models.DateTimeField(null=True, blank=True)
    assinado_ip = models.CharField(max_length=64, blank=True, default='')
    codigo_verificacao = models.CharField(max_length=12, blank=True, default='')
    hash_documento = models.CharField(max_length=64, blank=True, default='')
    hash_assinado = models.CharField(max_length=64, blank=True, default='')
    cpf_prefixo_hash = models.CharField(max_length=64, blank=True, default='')
    tentativas_identidade = models.PositiveSmallIntegerField(default=0)
    bloqueada_ate = models.DateTimeField(null=True, blank=True)
    revogada_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['prestacao', 'tipo']
        verbose_name = 'Assinatura de documento'
        verbose_name_plural = 'Assinaturas de documentos'
        constraints = [models.UniqueConstraint(fields=['prestacao', 'tipo'], condition=Q(servidor_prestacao__isnull=True) & ~Q(status='cancelada'), name='uniq_assinatura_prestacao_tipo'), models.UniqueConstraint(fields=['servidor_prestacao', 'tipo'], condition=Q(servidor_prestacao__isnull=False) & ~Q(status='cancelada'), name='uniq_assinatura_servidor_tipo'), models.UniqueConstraint(fields=['codigo_verificacao'], condition=~Q(codigo_verificacao=''), name='uniq_assinatura_codigo')]

    def __str__(self):
        return f'Assinatura {self.get_tipo_display()} — {self.prestacao_id}'

    @property
    def assinada(self) -> bool:
        return self.status == self.STATUS_ASSINADA and bool(self.arquivo_assinado)

    @property
    def link_expirado(self) -> bool:
        from django.utils import timezone as _tz
        return bool(self.link_expira_em and self.link_expira_em < _tz.now())

    @property
    def link_ativo(self) -> bool:
        return bool(self.link_token_hash) and not self.link_expirado and self.status == self.STATUS_PENDENTE

    @property
    def cpf_esperado(self) -> str:
        cpf = (self.signer.cpf or '').strip() if self.signer_id else ''
        return ''.join((ch for ch in cpf if ch.isdigit()))[:11]
