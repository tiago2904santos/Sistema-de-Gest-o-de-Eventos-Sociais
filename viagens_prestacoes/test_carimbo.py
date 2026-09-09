"""Carimbo do número de solicitação no ofício assinado do eProtocolo.

O que estes testes guardam, em ordem de importância:

1. **O número cai na linha do servidor**, mesmo quando o eProtocolo empurra o conteúdo.
   É a promessa inteira da feature: sem isso, o carimbo automático não vale nada e todo
   ofício precisaria de ajuste à mão.
2. **Carimbar duas vezes não duplica número.** O anexo é gravado carimbado, e o segundo
   carimbo tem de partir do cru — não do que já tem número impresso.
3. **Corrigir o número no cadastro atualiza o anexo.** O texto não é copiado para lugar
   nenhum; é lido na hora de desenhar.

Os PDFs são feitos aqui com reportlab, e não pelo motor de documentos: o que se mede é a
geometria do carimbo, não a diagramação do ofício, e amarrar o teste ao LibreOffice o
tornaria lento e dependente do que está instalado na máquina.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
from io import BytesIO
from unittest import mock
from django.core.files.uploadedfile import SimpleUploadedFile
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes import carimbo_services
from viagens_prestacoes.carimbo_services import agrupar_em_linhas
from viagens_prestacoes.carimbo_services import carimbar
from viagens_prestacoes.carimbo_services import ler_fragmentos
from viagens_prestacoes.carimbo_services import posicoes_automaticas
from viagens_prestacoes.carimbo_services import preparar_e_carimbar
from viagens_prestacoes.models import CarimboSolicitacao
from viagens_prestacoes.models import PrestacaoDocumentoAnexo
from viagens_prestacoes.solicitacao_services import salvar_solicitacao_do_autosave
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin
LARGURA, ALTURA = (595.0, 842.0)
COLUNA_NUMERO = 460.0
COLUNA_NOME = 60.0

def pdf_do_oficio(linhas, *, deslocamento=0.0, com_numero=True) -> bytes:
    """Um ofício de mentira: uma linha por servidor, nome à esquerda, número à direita.

    `deslocamento` empurra tudo para baixo, imitando o cabeçalho que o eProtocolo
    acrescenta — é essa a diferença que o transporte por âncora tem de absorver.
    """
    from reportlab.pdfgen import canvas
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(LARGURA, ALTURA))
    c.setFont('Helvetica', 10)
    y = 700.0 - deslocamento
    for nome, numero in linhas:
        c.drawString(COLUNA_NOME, y, nome)
        if com_numero and numero:
            c.drawString(COLUNA_NUMERO, y, numero)
        y -= 30.0
    c.save()
    return buffer.getvalue()

def textos_com_posicao(pdf: bytes) -> dict[str, tuple[float, float]]:
    return {f.texto: (round(f.x, 1), round(f.y, 1)) for f in ler_fragmentos(pdf)}

class LeituraDoPdfTests(TestCase):

    def test_le_o_texto_com_a_coordenada_em_que_foi_desenhado(self):
        pdf = pdf_do_oficio([('Joao Da Silva', '2026001234')])
        posicoes = textos_com_posicao(pdf)
        self.assertEqual(posicoes['Joao Da Silva'], (COLUNA_NOME, 700.0))
        self.assertEqual(posicoes['2026001234'], (COLUNA_NUMERO, 700.0))

    def test_agrupa_em_linhas_o_que_saiu_na_mesma_altura(self):
        pdf = pdf_do_oficio([('Joao Da Silva', '2026001234'), ('Maria Souza', '2026005678')])
        linhas = agrupar_em_linhas(ler_fragmentos(pdf))
        self.assertEqual([linha.texto for linha in linhas], ['Joao Da Silva 2026001234', 'Maria Souza 2026005678'])

    def test_pdf_sem_camada_de_texto_devolve_vazio_em_vez_de_estourar(self):
        """PDF escaneado é o caso em que o automático não tem como funcionar."""
        self.assertEqual(ler_fragmentos(pdf_do_oficio([])), [])

class PosicaoAutomaticaTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1, servidores=(self.criar_servidor('Joao Da Silva'), self.criar_servidor('Maria Souza')))
        self.prestacao = self.fixture.prestacao
        self.ps1, self.ps2 = self.fixture.prestacoes_servidor
        self.ps1.numero_solicitacao = '2026001234'
        self.ps1.save(update_fields=['numero_solicitacao'])
        self.ps2.numero_solicitacao = '2026005678'
        self.ps2.save(update_fields=['numero_solicitacao'])
        self.referencia = pdf_do_oficio([('Joao Da Silva', '2026001234'), ('Maria Souza', '2026005678')])

    def _posicoes(self, assinado):
        with mock.patch('viagens_prestacoes.services.gerar_oficio_prestacao_pdf', return_value=self.referencia):
            return posicoes_automaticas(self.prestacao, assinado)

    def test_sem_deslocamento_o_numero_cai_onde_a_referencia_o_tinha(self):
        assinado = pdf_do_oficio([('Joao Da Silva', ''), ('Maria Souza', '')], com_numero=False)
        posicoes = self._posicoes(assinado)
        self.assertEqual(round(posicoes[self.ps1.pk].x * LARGURA, 1), COLUNA_NUMERO)
        self.assertEqual(round((1 - posicoes[self.ps1.pk].y) * ALTURA, 1), 700.0)
        self.assertFalse(posicoes[self.ps1.pk].incerta)

    def test_deslocamento_do_eprotocolo_e_absorvido_pela_ancora(self):
        """O cabeçalho de protocolo empurra a página; a âncora anda junto com o número."""
        assinado = pdf_do_oficio([('Joao Da Silva', ''), ('Maria Souza', '')], deslocamento=57.0, com_numero=False)
        posicoes = self._posicoes(assinado)
        self.assertEqual(round((1 - posicoes[self.ps1.pk].y) * ALTURA, 1), 643.0)
        self.assertEqual(round((1 - posicoes[self.ps2.pk].y) * ALTURA, 1), 613.0)

    def test_sem_ancora_no_destino_recusa_sem_copiar_coordenada(self):
        with self.assertRaises(carimbo_services.CarimboError):
            self._posicoes(pdf_do_oficio([('Pessoa diferente', '')], com_numero=False))

    def test_servidor_sem_numero_fica_de_fora(self):
        self.ps2.numero_solicitacao = ''
        self.ps2.save(update_fields=['numero_solicitacao'])
        assinado = pdf_do_oficio([('Joao Da Silva', '')], com_numero=False)
        posicoes = self._posicoes(assinado)
        self.assertIn(self.ps1.pk, posicoes)
        self.assertNotIn(self.ps2.pk, posicoes)

class AplicacaoDoCarimboTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=2, servidores=(self.criar_servidor('Joao Da Silva'),))
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        self.ps.numero_solicitacao = '2026001234'
        self.ps.save(update_fields=['numero_solicitacao'])
        cru = pdf_do_oficio([('Joao Da Silva', '')], com_numero=False)
        self.anexo = PrestacaoDocumentoAnexo.objects.create(prestacao=self.prestacao, tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO, arquivo=SimpleUploadedFile('oficio.pdf', cru, content_type='application/pdf'), arquivo_original=SimpleUploadedFile('oficio_cru.pdf', cru, content_type='application/pdf'), nome_original='oficio.pdf')
        CarimboSolicitacao.objects.create(anexo=self.anexo, servidor_prestacao=self.ps, pagina=0, x=COLUNA_NUMERO / LARGURA, y=(ALTURA - 700.0) / ALTURA, tamanho=10.0 / ALTURA)

    def _texto_do_anexo(self) -> dict[str, tuple[float, float]]:
        self.anexo.refresh_from_db()
        self.anexo.arquivo.open('rb')
        try:
            return textos_com_posicao(self.anexo.arquivo.read())
        finally:
            self.anexo.arquivo.close()

    def test_o_numero_sai_na_linha_do_servidor(self):
        resultado = carimbar(self.anexo)
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.carimbados, 1)
        self.assertEqual(self._texto_do_anexo()['2026001234'], (COLUNA_NUMERO, 700.0))

    def test_carimbar_duas_vezes_nao_duplica_o_numero(self):
        """O segundo carimbo parte do cru; partir do carimbado empilharia os dois."""
        carimbar(self.anexo)
        carimbar(self.anexo)
        self.anexo.refresh_from_db()
        self.anexo.arquivo.open('rb')
        try:
            fragmentos = ler_fragmentos(self.anexo.arquivo.read())
        finally:
            self.anexo.arquivo.close()
        self.assertEqual(sum((1 for f in fragmentos if f.texto == '2026001234')), 1)

    def test_o_pdf_cru_fica_intocado(self):
        carimbar(self.anexo)
        self.anexo.refresh_from_db()
        self.anexo.arquivo_original.open('rb')
        try:
            cru = ler_fragmentos(self.anexo.arquivo_original.read())
        finally:
            self.anexo.arquivo_original.close()
        self.assertNotIn('2026001234', [f.texto for f in cru])

    def test_servidor_sem_numero_entra_na_pendencia_e_nao_e_desenhado(self):
        self.ps.numero_solicitacao = ''
        self.ps.save(update_fields=['numero_solicitacao'])
        resultado = carimbar(self.anexo)
        self.assertEqual(resultado.carimbados, 0)
        self.assertEqual(resultado.sem_numero, [self.ps.servidor.nome])

    def test_corrigir_o_numero_atualiza_o_anexo(self):
        """O texto não é copiado: é lido de `numero_solicitacao` na hora de desenhar."""
        carimbar(self.anexo)
        self.ps.numero_solicitacao = '2026009999'
        self.ps.save(update_fields=['numero_solicitacao'])
        carimbar(self.anexo)
        textos = self._texto_do_anexo()
        self.assertIn('2026009999', textos)
        self.assertNotIn('2026001234', textos)

class FluxoDoUploadTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=3, servidores=(self.criar_servidor('Joao Da Silva'),))
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        self.ps.numero_solicitacao = '2026001234'
        self.ps.save(update_fields=['numero_solicitacao'])
        self.referencia = pdf_do_oficio([('Joao Da Silva', '2026001234')])

    def _anexar(self):
        cru = pdf_do_oficio([('Joao Da Silva', '')], com_numero=False)
        with mock.patch('viagens_prestacoes.services.gerar_oficio_prestacao_pdf', return_value=self.referencia):
            return self.client.post(reverse('viagens_prestacoes:prestacao_oficio_assinado_anexar', args=[self.prestacao.pk]), {'arquivo': SimpleUploadedFile('oficio assinado.pdf', cru, content_type='application/pdf')})

    def test_anexar_ja_grava_o_numero_e_guarda_o_cru(self):
        self._anexar()
        anexo = self.prestacao.documentos_anexos.get(tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO)
        self.assertTrue(anexo.arquivo_original)
        self.assertEqual(anexo.carimbos.count(), 1)
        anexo.arquivo.open('rb')
        try:
            textos = [f.texto for f in ler_fragmentos(anexo.arquivo.read())]
        finally:
            anexo.arquivo.close()
        self.assertIn('2026001234', textos)

    def test_servidor_sem_numero_nao_bloqueia_o_upload(self):
        self.ps.numero_solicitacao = ''
        self.ps.save(update_fields=['numero_solicitacao'])
        resposta = self._anexar()
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(self.prestacao.documentos_anexos.filter(tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO).exists())

    def test_a_tela_de_ajuste_grava_posicao_e_marca_como_manual(self):
        self._anexar()
        anexo = self.prestacao.documentos_anexos.get(tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO)
        self.client.post(reverse('viagens_prestacoes:prestacao_carimbo_ajustar', args=[self.prestacao.pk]), {f'caixa-{self.ps.pk}-pagina': '0', f'caixa-{self.ps.pk}-x': '0.5', f'caixa-{self.ps.pk}-y': '0.5', f'caixa-{self.ps.pk}-tamanho': '0.02'})
        carimbo = anexo.carimbos.get()
        self.assertTrue(carimbo.ajustado_manualmente)
        self.assertAlmostEqual(carimbo.x, 0.5)
        anexo.refresh_from_db()
        anexo.arquivo.open('rb')
        try:
            posicoes = textos_com_posicao(anexo.arquivo.read())
        finally:
            anexo.arquivo.close()
        self.assertEqual(posicoes['2026001234'], (LARGURA / 2, ALTURA / 2))

    def test_posicao_manual_sobrevive_a_um_novo_upload(self):
        """O automático já errou ali uma vez; reescrever devolveria o erro corrigido."""
        self._anexar()
        anexo = self.prestacao.documentos_anexos.get(tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO)
        anexo.carimbos.update(ajustado_manualmente=True, x=0.5, y=0.5)
        with mock.patch('viagens_prestacoes.services.gerar_oficio_prestacao_pdf', return_value=self.referencia):
            preparar_e_carimbar(anexo, prestacao=self.prestacao)
        self.assertAlmostEqual(anexo.carimbos.get().x, 0.5)

    def test_mudar_o_numero_recarimba_o_anexo_sozinho(self):
        self._anexar()
        anexo = self.prestacao.documentos_anexos.get(tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO)
        with self.captureOnCommitCallbacks(execute=True):
            salvar_solicitacao_do_autosave(self.ps, numero='2026007777')
        anexo.refresh_from_db()
        anexo.arquivo.open('rb')
        try:
            textos = [f.texto for f in ler_fragmentos(anexo.arquivo.read())]
        finally:
            anexo.arquivo.close()
        self.assertIn('2026007777', textos)
        self.assertNotIn('2026001234', textos)

class TelaDeAjusteTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=4, servidores=(self.criar_servidor('Joao Da Silva'),))
        self.prestacao = self.fixture.prestacao

    def test_sem_oficio_anexado_a_tela_manda_anexar_antes(self):
        resposta = self.client.get(reverse('viagens_prestacoes:prestacao_carimbo_ajustar', args=[self.prestacao.pk]))
        self.assertEqual(resposta.status_code, 302)

    def test_a_tela_serve_o_pdf_cru_e_nao_o_carimbado(self):
        """Mostrar o carimbado faria o operador ver dois números: o impresso e a caixa."""
        cru = pdf_do_oficio([('Joao Da Silva', '')], com_numero=False)
        PrestacaoDocumentoAnexo.objects.create(prestacao=self.prestacao, tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO, arquivo=SimpleUploadedFile('carimbado.pdf', pdf_do_oficio([('Joao Da Silva', '2026001234')]), content_type='application/pdf'), arquivo_original=SimpleUploadedFile('cru.pdf', cru, content_type='application/pdf'))
        resposta = self.client.get(reverse('viagens_prestacoes:prestacao_oficio_assinado_cru', args=[self.prestacao.pk]))
        conteudo = b''.join(resposta.streaming_content) if resposta.streaming else resposta.content
        self.assertNotIn('2026001234', [f.texto for f in ler_fragmentos(conteudo)])

    def test_recarimbo_sem_anexo_nao_faz_nada(self):
        self.assertIsNone(carimbo_services.recarimbar_prestacao(self.prestacao))
