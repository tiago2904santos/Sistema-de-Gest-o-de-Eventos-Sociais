from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
from io import StringIO
from tempfile import TemporaryDirectory
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from .test_helpers import PrestacaoTestCase as TestCase
from django.test import override_settings
from viagens_prestacoes.models import PrestacaoDocumentoAnexo
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin

class LimparArquivosOrfaosTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self._media = TemporaryDirectory()
        self._override_media = override_settings(MEDIA_ROOT=self._media.name)
        self._override_media.enable()
        self.addCleanup(self._override_media.disable)
        self.addCleanup(self._media.cleanup)
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=104)

    def executar(self, *args):
        saida = StringIO()
        call_command('limpar_arquivos_orfaos', *args, stdout=saida)
        return saida.getvalue()

    def criar_orfao(self):
        return default_storage.save('viagens_prestacoes/104/orfao.pdf', ContentFile(b'arquivo sem linha'))

    def test_diagnostico_lista_orfao_sem_apagar(self):
        nome = self.criar_orfao()
        saida = self.executar()
        self.assertIn(f'Arquivo órfão: {nome}', saida)
        self.assertIn('nada foi apagado', saida)
        self.assertTrue(default_storage.exists(nome))

    def test_apagar_remove_somente_o_orfao(self):
        anexo = PrestacaoDocumentoAnexo.objects.create(prestacao=self.fixture.prestacao, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE, arquivo=ContentFile(b'arquivo vivo', name='vivo.pdf'), nome_original='vivo.pdf')
        orfao = self.criar_orfao()
        saida = self.executar('--apagar')
        self.assertIn('Removidos 1 arquivo(s) órfão(s).', saida)
        self.assertFalse(default_storage.exists(orfao))
        self.assertTrue(default_storage.exists(anexo.arquivo.name))

    def test_documento_de_outro_filefield_na_mesma_pasta_nao_e_orfao(self):
        prestacao = self.fixture.prestacao
        prestacao.despacho_assinado.save('despacho.pdf', ContentFile(b'despacho vivo'))
        saida = self.executar()
        self.assertEqual(saida.strip(), 'Nenhum arquivo órfão encontrado.')
        self.assertTrue(default_storage.exists(prestacao.despacho_assinado.name))
