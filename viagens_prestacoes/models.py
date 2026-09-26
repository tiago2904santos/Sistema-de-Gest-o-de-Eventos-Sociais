from core.legado import OrigemLegado
from django.conf import settings
from django.db import models
from .arquivos import ArquivoPrivadoField
from core.constraints import periodo_ordenado
from core.constraints import positivo
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

def importacao_processo_upload_to(instance, filename):
    """O processo inteiro do eProtocolo, como foi enviado para importar.

    Fica fora da pasta de uma prestação porque, quando chega, ainda não se sabe de
    qual ela é — e pode nem vir a ser de nenhuma (importação descartada).
    """
    from django.utils import timezone
    return f"viagens_prestacoes/importacoes/{timezone.localdate():%Y/%m}/{filename}"

class PrestacaoContas(OrigemLegado):
    STATUS_PENDENTE = 'pendente'
    STATUS_EM_PREENCHIMENTO = 'em_preenchimento'
    STATUS_ENVIADA = 'enviada'
    STATUS_APROVADA = 'aprovada'
    STATUS_REPROVADA = 'reprovada'
    STATUS_CHOICES = [(STATUS_PENDENTE, 'Pendente'), (STATUS_EM_PREENCHIMENTO, 'Em preenchimento'), (STATUS_ENVIADA, 'Enviada'), (STATUS_APROVADA, 'Aprovada'), (STATUS_REPROVADA, 'Devolvida')]
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
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_prestacaocontas_origem")]

    def __str__(self):
        return f'Prestação — Ofício {self.oficio.numero_formatado}'

class PrestacaoServidorAtivosManager(models.Manager):
    """Manager padrão de registros ativos; ``todos`` inclui remoções reversíveis."""

    def get_queryset(self):
        return super().get_queryset().filter(removida_em__isnull=True)

class PrestacaoServidor(OrigemLegado):
    """Parte individual da prestação de um servidor dentro do ofício.

    Guarda o acompanhamento e o que muda de servidor para servidor: status,
    arquivamento/finalização, número da solicitação, comprovante de saque/
    transferência (via ``PrestacaoDocumentoAnexo``). O texto do RT e o diário de bordo são
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
    #: m092: por que foi finalizada com pendências (vazio = sem pendência).
    justificativa_finalizacao = models.TextField('Justificativa para finalizar com pendências', blank=True, default='')
    #: m093: envio ao financeiro e a decisão (aprovada ou devolvida para correção).
    enviada_em = models.DateField('Enviada em', null=True, blank=True)
    protocolo_envio = models.CharField('Protocolo ou e-mail do envio', max_length=120, blank=True, default='')
    decidida_em = models.DateTimeField('Aprovada ou devolvida em', null=True, blank=True)
    motivo_devolucao = models.TextField('Motivo da devolução', blank=True, default='')
    removida_em = models.DateTimeField('Removida da equipe em', null=True, blank=True)
    #: m099: ajuste manual do pacote final — ordem, giro e páginas ocultas. Vale só
    #: enquanto a `assinatura` (documentos e número de páginas) bater; mudou um
    #: anexo, o ajuste é descartado. Formato em `services.aplicar_ajuste_do_pacote`.
    ajuste_pacote = models.JSONField('Ajuste manual do pacote final', default=dict, blank=True)
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
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_prestacaoservidor_origem"), models.UniqueConstraint(fields=['prestacao', 'servidor'], name='unique_servidor_por_prestacao'), positivo('diaria_valor_override', name='prest_serv_diaria_recebida_positiva'), periodo_ordenado('data_liberacao_diarias', 'prazo_limite_saque', name='prest_serv_prazo_apos_liberacao')]

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

    def definir_finalizada(self, finalizada: bool, *, justificativa: str | None = None):
        """Conclui/reabre a prestação deste servidor, registrando o momento.

        `justificativa` (m092) é gravada quando se finaliza com pendências; finalizar
        sem pendência (`""`) apaga a de uma finalização anterior. `None` não mexe.
        """
        from django.utils import timezone as _tz
        self.finalizada = finalizada
        self.finalizada_em = _tz.now() if finalizada else None
        campos = ['finalizada', 'finalizada_em', 'atualizado_em']
        if justificativa is not None:
            self.justificativa_finalizacao = justificativa
            campos.append('justificativa_finalizacao')
        self.save(update_fields=campos)

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
        # A linha histórica importada deve continuar rastreável no diário da
        # migração, mesmo quando ainda não tem preenchimento financeiro.
        return bool(self.legado_pk is not None or self.numero_solicitacao.strip() or self.diaria_valor_override is not None or self.diaria_valor_override_observacao.strip() or self.data_liberacao_diarias or self.prazo_limite_saque or (self.status != self.STATUS_PENDENTE) or self.arquivada or self.finalizada or self.justificativa_finalizacao.strip() or self.enviada_em or self.protocolo_envio.strip() or self.decidida_em or self.motivo_devolucao.strip() or self.documentos_anexos.exists())

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

        Aqui ficam os dois que, apagados, não voltam: o arquivo do comprovante e o
        número da solicitação digitado à mão.
        """
        return bool(self.documentos_anexos.exists() or self.numero_solicitacao.strip())

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
        """Desfaz `sair_da_equipe`, e com ela reaparecem os anexos."""
        if self.removida_em is None:
            return
        self.removida_em = None
        self.save(update_fields=['removida_em', 'atualizado_em'])

class AnexosAtivosManager(models.Manager):
    """Anexos em uso; ``todos`` inclui os removidos e os substituídos (m084)."""

    def get_queryset(self):
        return super().get_queryset().filter(removido_em__isnull=True)

#: Por quantos dias o anexo removido ou substituído fica em "Versões anteriores"
#: antes de `limpar_arquivos_orfaos --apagar` apagá-lo de vez.
DIAS_GUARDA_ANEXO_REMOVIDO = 30

#: Como o dinheiro chegou ao servidor, lido do comprovante bancário.
OPERACAO_CHOICES = [('saque', 'Saque'), ('transferencia', 'Transferência'), ('pix', 'Pix'), ('ted', 'TED'), ('doc', 'DOC'), ('deposito', 'Depósito')]

class PrestacaoDocumentoAnexo(OrigemLegado):
    TIPO_DESPACHO = 'despacho'
    TIPO_OFICIO_ASSINADO = 'oficio_assinado'
    TIPO_COMPROVANTE = 'comprovante'
    TIPO_RT_ASSINADO = 'rt_assinado'
    TIPO_DB_ASSINADO = 'db_assinado'
    TIPO_CHOICES = [(TIPO_DESPACHO, 'Despacho assinado do ofício'), (TIPO_OFICIO_ASSINADO, 'Ofício assinado'), (TIPO_COMPROVANTE, 'Comprovante de saque/transferência'), (TIPO_RT_ASSINADO, 'Relatório técnico assinado'), (TIPO_DB_ASSINADO, 'Diário de bordo assinado')]
    #: Os tipos que têm um arquivo só: anexar de novo substitui. Despacho e
    #: comprovante somam (m081).
    TIPOS_UNICOS = (TIPO_OFICIO_ASSINADO, TIPO_RT_ASSINADO, TIPO_DB_ASSINADO)
    REMOVIDO_EXCLUIDO = 'excluido'
    REMOVIDO_SUBSTITUIDO = 'substituido'
    REMOVIDO_CHOICES = [(REMOVIDO_EXCLUIDO, 'Removido'), (REMOVIDO_SUBSTITUIDO, 'Substituído')]
    prestacao = models.ForeignKey(PrestacaoContas, on_delete=models.CASCADE, related_name='documentos_anexos')
    servidor_prestacao = models.ForeignKey(PrestacaoServidor, on_delete=models.CASCADE, null=True, blank=True, related_name='documentos_anexos')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    arquivo = ArquivoPrivadoField(upload_to=prestacao_documento_anexo_upload_to, validators=[validate_private_document_upload])
    arquivo_original = ArquivoPrivadoField(upload_to=prestacao_anexo_original_upload_to, blank=True, help_text='PDF como enviado, antes do carimbo. Origem de todo recarimbo.')
    nome_original = models.CharField(max_length=255, blank=True, default='')
    #: De qual importação de processo o anexo saiu (vazio = anexado à mão).
    importacao = models.ForeignKey('ImportacaoProcesso', on_delete=models.SET_NULL, null=True, blank=True, related_name='anexos')
    #: Folhas do processo de onde o anexo foi recortado, na numeração do PDF ("3-4", "7, 9").
    paginas_origem = models.CharField('páginas no processo', max_length=60, blank=True, default='')
    #: Comprovante: quanto foi sacado/transferido, em que dia e como. Vários
    #: comprovantes por servidor, cada um com os seus — por isso ficam no anexo, e
    #: não em `PrestacaoServidor`.
    valor = models.DecimalField('valor da operação', max_digits=10, decimal_places=2, null=True, blank=True)
    data_operacao = models.DateField('data da operação', null=True, blank=True)
    operacao = models.CharField('operação', max_length=20, choices=OPERACAO_CHOICES, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    #: m084: remover ou substituir só marca a linha; o arquivo fica em "Versões
    #: anteriores" por `DIAS_GUARDA_ANEXO_REMOVIDO` dias, e dá para voltar a ele.
    removido_em = models.DateTimeField('removido em', null=True, blank=True)
    removido_motivo = models.CharField('motivo da remoção', max_length=12, choices=REMOVIDO_CHOICES, blank=True, default='')
    objects = AnexosAtivosManager()
    todos = models.Manager()

    @property
    def arquivo_para_carimbar(self):
        """De onde o carimbo parte: o cru quando existe, senão o próprio arquivo.

        O `or` cobre os anexos criados antes deste campo — carimbá-los uma vez é
        correto; o segundo carimbo é que duplicaria, e a partir da primeira vez o cru
        passa a existir.
        """
        return self.arquivo_original if self.arquivo_original else self.arquivo

    class Meta:
        default_manager_name = 'objects'
        ordering = ['tipo', 'criado_em', 'pk']
        verbose_name = 'Anexo da prestação de contas'
        verbose_name_plural = 'Anexos da prestação de contas'
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_prestacaodocumentoanexo_origem"), positivo('valor', name='prest_anexo_valor_positivo')]

    def __str__(self):
        return self.nome_original or self.arquivo.name

#: A ordem dos documentos da prestação, a mesma em todo lugar que os junta ou lista:
#: pacote final, "Baixar documentos", modal de anexar e Etapa 3. Ofício → despacho(s)
#: com a folha de assinatura → relatório técnico → diário de bordo → comprovante(s).
ORDEM_DOCUMENTOS_PRESTACAO = (
    PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO,
    PrestacaoDocumentoAnexo.TIPO_DESPACHO,
    PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO,
    PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO,
    PrestacaoDocumentoAnexo.TIPO_COMPROVANTE,
)


def ordenacao_dos_anexos(tipo) -> tuple:
    """Como ordenar os anexos de um tipo dentro do pacote.

    Comprovantes pela data da operação (o saque antes da transferência do dia
    seguinte), os sem data no fim; o resto — e o desempate — pela ordem em que foram
    anexados, que no importador é a ordem do processo.
    """
    if tipo == PrestacaoDocumentoAnexo.TIPO_COMPROVANTE:
        return (models.F('data_operacao').asc(nulls_last=True), 'criado_em', 'pk')
    return ('criado_em', 'pk')

class ImportacaoProcesso(OrigemLegado):
    """Um processo do eProtocolo enviado para importar na prestação de contas.

    Guarda o PDF como veio (auditoria e "aplicar de novo"), o hash contra importar
    o mesmo arquivo duas vezes, o que a leitura propôs (`plano`) e o que foi gravado
    (`resultado`). O `plano` não leva texto do documento nem CPF: só tipo, páginas,
    destino e os dados que vão para o anexo (valor, data, operação do comprovante).
    """
    SITUACAO_ANALISADA = 'analisada'
    SITUACAO_APLICADA = 'aplicada'
    SITUACAO_DESCARTADA = 'descartada'
    SITUACAO_CHOICES = [(SITUACAO_ANALISADA, 'Aguardando conferência'), (SITUACAO_APLICADA, 'Aplicada'), (SITUACAO_DESCARTADA, 'Descartada')]
    arquivo = ArquivoPrivadoField('processo enviado', upload_to=importacao_processo_upload_to)
    nome_original = models.CharField(max_length=255, blank=True, default='')
    hash_sha256 = models.CharField('SHA-256 do arquivo', max_length=64, db_index=True)
    protocolo = models.CharField('protocolo lido', max_length=30, blank=True, default='')
    oficio = models.ForeignKey(Oficio, on_delete=models.SET_NULL, null=True, blank=True, related_name='importacoes_processo')
    prestacao = models.ForeignKey(PrestacaoContas, on_delete=models.SET_NULL, null=True, blank=True, related_name='importacoes')
    situacao = models.CharField(max_length=20, choices=SITUACAO_CHOICES, default=SITUACAO_ANALISADA, db_index=True)
    plano = models.JSONField(default=dict, blank=True)
    resultado = models.JSONField(default=dict, blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    criado_em = models.DateTimeField(auto_now_add=True)
    aplicado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-criado_em', '-pk']
        verbose_name = 'Importação de processo'
        verbose_name_plural = 'Importações de processo'
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_importacaoprocesso_origem")]

    def __str__(self):
        return self.nome_original or self.arquivo.name

class CarimboSolicitacao(OrigemLegado):
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
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_carimbosolicitacao_origem"), models.UniqueConstraint(fields=['anexo', 'servidor_prestacao'], name='carimbo_unico_por_servidor_no_anexo')]
        ordering = ['pagina', 'y', 'x', 'pk']
        verbose_name = 'Carimbo do número de solicitação'
        verbose_name_plural = 'Carimbos do número de solicitação'

    def __str__(self):
        return f'carimbo p{self.pagina} de {self.servidor_prestacao_id}'

class RelatorioTecnico(OrigemLegado):
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
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_relatoriotecnico_origem")]

    def __str__(self):
        return f'RT — {self.prestacao}'

class DiarioBordo(OrigemLegado):
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
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_diariobordo_origem")]

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

class DiarioBordoTrecho(OrigemLegado):
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
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_diariobordotrecho_origem"), models.UniqueConstraint(fields=['diario', 'ordem'], name='diario_trecho_ordem_unique'), periodo_ordenado('km_inicial', 'km_final', name='diario_trecho_km_ordenado', mensagem='O km final não pode ser menor que o km inicial.')]

    def __str__(self):
        return f'Trecho {self.ordem} — {self.diario_id}'

class ModeloTextoRelatorioTecnico(OrigemLegado):
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

    class Meta:
        ordering = ['campo', 'nome']
        verbose_name = 'Modelo de texto do RT'
        verbose_name_plural = 'Modelos de texto do RT'
        constraints = [models.UniqueConstraint(fields=["legado_origem", "legado_pk"], condition=models.Q(legado_pk__isnull=False), name="f6_modelotextorelatoriotecnico_origem"), models.UniqueConstraint(fields=['campo', 'nome'], name='unique_modelo_texto_rt_campo_nome')]

    def __str__(self):
        return f'{self.get_campo_display()} — {self.nome}'
