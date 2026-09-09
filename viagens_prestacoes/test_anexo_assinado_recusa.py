"""A recusa do anexo assinado tem de chegar a quem anexou.

`NOVO-20260824-133423-35fbd4d59a84` — o modal envia por `fetch` quando há mais de
um documento na mesma janela. A view respondia com redirect e `messages.error`; o
`fetch` seguia o redirect, a página de destino era renderizada dentro da resposta
do XHR e renderizar CONSOME as mensagens. O modal via `response.ok` verdadeiro,
recarregava a tela e o operador ficava com um arquivo não anexado e nenhuma
palavra sobre o motivo.

Para o XHR a recusa agora é 400 com o motivo no corpo. O caminho de formulário
comum — um documento só, submit nativo — continua sendo mensagem + redirect, e
está fixado aqui para não regredir junto.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from .test_helpers import PrestacaoTestCase as TestCase
from django.test import override_settings
from django.urls import reverse
from viagens_prestacoes.models import PrestacaoDocumentoAnexo
from viagens_prestacoes.test_helpers import PDF_MINIMO
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin
NAO_E_PDF = b'isto nao e um PDF, apesar do sufixo'

class AnexoAssinadoRecusaTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        self.url = reverse('viagens_prestacoes:prestacao_despacho_assinado_anexar', args=[self.prestacao.pk])

    def _post(self, dados, *, xhr):
        cabecalhos = {'headers': {'x-requested-with': 'XMLHttpRequest'}} if xhr else {}
        return self.client.post(self.url, dados, **cabecalhos)

    def test_xhr_recebe_400_com_o_motivo_quando_o_arquivo_nao_e_pdf(self):
        response = self._post({'arquivo': SimpleUploadedFile('despacho.pdf', NAO_E_PDF, content_type='application/pdf')}, xhr=True)
        self.assertEqual(response.status_code, 400)
        corpo = response.json()
        self.assertFalse(corpo['ok'])
        self.assertIn('PDF', corpo['error'])
        self.assertFalse(self.prestacao.documentos_anexos.exists())

    def test_xhr_sem_arquivo_recebe_400_e_nao_um_redirect_silencioso(self):
        response = self._post({}, xhr=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Selecione um arquivo', response.json()['error'])

    def test_xhr_bem_sucedido_responde_json_e_guarda_a_mensagem_para_o_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            response = self._post({'arquivo': SimpleUploadedFile('despacho.pdf', PDF_MINIMO, content_type='application/pdf')}, xhr=True)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['ok'])
            anexo = self.prestacao.documentos_anexos.get()
            self.assertEqual(anexo.tipo, PrestacaoDocumentoAnexo.TIPO_DESPACHO)
            seguinte = self.client.get(reverse('viagens_prestacoes:index'))
            self.assertContains(seguinte, 'Documento assinado anexado.')

    def test_formulario_comum_continua_com_mensagem_e_redirect(self):
        response = self.client.post(self.url, {'arquivo': SimpleUploadedFile('despacho.pdf', NAO_E_PDF, content_type='application/pdf')})
        self.assertEqual(response.status_code, 302)
        mensagens = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any(('PDF' in m for m in mensagens)), mensagens)
