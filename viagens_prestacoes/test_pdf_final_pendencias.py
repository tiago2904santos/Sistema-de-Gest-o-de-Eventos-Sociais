"""O PDF Final diz o que falta antes de prometer um arquivo.

`NOVO-20260824-133423-10943c04a7c5` — o fechamento calculava `numero_ok` e não
usava em lugar nenhum. Sem número de solicitação, sem despacho assinado ou sem
comprovante, a geração é recusada pelo serviço; a tela, porém, oferecia o
download e o clique caía numa página que dizia "a geração continua em segundo
plano" para um arquivo que ninguém estava gerando
(`NOVO-20260824-133423-ade2a3103cc3`).

Os testes prendem as duas pontas juntas: o que o fechamento mostra, no fim da
etapa de Documentos, é exatamente o que `gerar_prestacao_consolidado_pdf` cobra.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from .test_helpers import PrestacaoTestCase as TestCase
from django.test import override_settings
from django.urls import reverse
from documentos.services.exceptions import DocumentValidationError
from viagens_prestacoes.models import PrestacaoDocumentoAnexo
from viagens_prestacoes.services import gerar_prestacao_consolidado_pdf
from viagens_prestacoes.services import pendencias_consolidado
from viagens_prestacoes.test_helpers import PDF_MINIMO
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin

class PdfFinalPendenciasTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        self.url = reverse('viagens_prestacoes:documentos_servidor', args=[self.ps.pk])

    def _anexar(self, tipo, *, do_servidor=False, nome='arquivo.pdf'):
        return PrestacaoDocumentoAnexo.objects.create(prestacao=self.prestacao, servidor_prestacao=self.ps if do_servidor else None, tipo=tipo, arquivo=SimpleUploadedFile(nome, PDF_MINIMO, content_type='application/pdf'), nome_original=nome)

    def _completar(self):
        self.ps.numero_solicitacao = 'SOL-1'
        self.ps.save(update_fields=['numero_solicitacao', 'atualizado_em'])
        self._anexar(PrestacaoDocumentoAnexo.TIPO_DESPACHO, nome='despacho.pdf')
        self._anexar(PrestacaoDocumentoAnexo.TIPO_COMPROVANTE, do_servidor=True, nome='comprovante.pdf')

    def test_prestacao_vazia_tem_as_tres_pendencias(self):
        pendencias = pendencias_consolidado(self.ps)
        self.assertEqual(len(pendencias), 3)
        self.assertTrue(any(('número da solicitação' in p for p in pendencias)))
        self.assertTrue(any(('despacho assinado' in p for p in pendencias)))
        self.assertTrue(any(('comprovante' in p for p in pendencias)))

    def test_pendencia_some_conforme_a_etapa_documentos_e_preenchida(self):
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            self.ps.numero_solicitacao = 'SOL-1'
            self.ps.save(update_fields=['numero_solicitacao', 'atualizado_em'])
            self.assertEqual(len(pendencias_consolidado(self.ps)), 2)
            self._anexar(PrestacaoDocumentoAnexo.TIPO_DESPACHO, nome='despacho.pdf')
            self.assertEqual(len(pendencias_consolidado(self.ps)), 1)
            self._anexar(PrestacaoDocumentoAnexo.TIPO_COMPROVANTE, do_servidor=True, nome='comprovante.pdf')
            self.assertEqual(pendencias_consolidado(self.ps), [])

    def test_geracao_recusa_com_o_mesmo_texto_que_a_tela_mostra(self):
        """Uma lista só para as duas pontas — divergir aqui é o defeito antigo."""
        with self.assertRaises(DocumentValidationError) as erro:
            gerar_prestacao_consolidado_pdf(self.ps)
        for pendencia in pendencias_consolidado(self.ps):
            self.assertIn(pendencia, str(erro.exception))

    def test_fechamento_lista_as_pendencias_e_nao_oferece_o_download(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['pendencias'])
        self.assertContains(response, 'Falta para o pacote final')
        # Com pendência, o pacote final aparece no menu, mas apagado e sem link.
        self.assertNotContains(response, reverse('viagens_prestacoes:consolidado_download', args=[self.ps.pk]))

    def test_fechamento_volta_a_oferecer_o_pacote_quando_nada_falta(self):
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            self._completar()
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pendencias'], [])
        self.assertContains(response, reverse('viagens_prestacoes:consolidado_download', args=[self.ps.pk]))
        self.assertNotContains(response, 'Falta para o pacote final')

    def test_download_com_pendencia_diz_o_motivo_em_vez_de_prometer_o_arquivo(self):
        response = self.client.get(reverse('viagens_prestacoes:consolidado_download', args=[self.ps.pk]))
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, 'Não foi possível gerar o documento', status_code=422)
        self.assertContains(response, 'número da solicitação', status_code=422)
        self.assertNotContains(response, 'o download começa sozinho', status_code=422)
