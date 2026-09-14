import tempfile
from pathlib import Path

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings
from pypdf import PdfWriter

from migracao_legado.arquivos import caminho_contido, copiar_arquivo, planejar_arquivo, quarentenar, sha256


class ArquivosTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.origem = self.raiz / 'origem'
        self.origem.mkdir()
        self.destino = self.raiz / 'destino'
        self.quarentena = self.raiz / 'quarentena'
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.write(self.origem / 'prova.pdf')

    def test_simular_valida_sem_gravar_nada(self):
        antes = {str(p): p.read_bytes() for p in self.raiz.rglob('*') if p.is_file()}
        plano = planejar_arquivo(self.origem, 'prova.pdf')
        self.assertEqual(plano.hash, sha256(self.origem / 'prova.pdf'))
        self.assertEqual(antes, {str(p): p.read_bytes() for p in self.raiz.rglob('*') if p.is_file()})
        self.assertFalse(self.destino.exists())

    def test_copia_preserva_binario_e_e_idempotente(self):
        plano = planejar_arquivo(self.origem, 'prova.pdf')
        nome, criou = copiar_arquivo(plano, self.destino)
        self.assertTrue(criou)
        self.assertEqual((self.destino / nome).read_bytes(), (self.origem / 'prova.pdf').read_bytes())
        self.assertEqual(copiar_arquivo(plano, self.destino), (nome, False))

    def test_destino_diferente_nunca_e_sobrescrito(self):
        plano = planejar_arquivo(self.origem, 'prova.pdf')
        nome, _ = copiar_arquivo(plano, self.destino)
        (self.destino / nome).write_bytes(b'nativo')
        with self.assertRaisesMessage(ValidationError, 'conteúdo diferente'):
            copiar_arquivo(plano, self.destino)
        self.assertEqual((self.destino / nome).read_bytes(), b'nativo')

    def test_hash_incorreto_reprova(self):
        with self.assertRaisesMessage(ValidationError, 'SHA-256'):
            planejar_arquivo(self.origem, 'prova.pdf', 'a' * 64)

    def test_origem_mudou_durante_copia_compensa_arquivo(self):
        plano = planejar_arquivo(self.origem, 'prova.pdf')
        (self.origem / 'prova.pdf').write_bytes(b'mudou')
        with self.assertRaisesMessage(ValidationError, 'mudou durante'):
            copiar_arquivo(plano, self.destino)
        self.assertFalse((self.destino / plano.nome).exists())

    def test_reprovado_fica_na_quarentena_e_simulacao_nao_copia(self):
        (self.origem / 'quebrado.pdf').write_bytes(b'nao e PDF')
        with self.assertRaises(ValidationError):
            planejar_arquivo(self.origem, 'quebrado.pdf')
        previsto = quarentenar(self.origem, 'quebrado.pdf', self.quarentena)
        self.assertEqual(previsto['situacao'], 'quarentena_prevista')
        self.assertFalse(self.quarentena.exists())
        feito = quarentenar(self.origem, 'quebrado.pdf', self.quarentena, commit=True)
        self.assertEqual((self.quarentena / feito['arquivo']).read_bytes(), b'nao e PDF')
        self.assertTrue((self.origem / 'quebrado.pdf').exists())

    def test_caminhos_nao_escapam_da_raiz(self):
        for nome in ['../segredo', '/segredo', 'C:/segredo', r'..\segredo', '']:
            with self.subTest(nome=nome), self.assertRaises(ValidationError):
                caminho_contido(self.origem, nome)

    @override_settings(PRIVATE_UPLOAD_MAX_BYTES=10)
    def test_limite_de_tamanho_do_sistema(self):
        with self.assertRaisesMessage(ValidationError, 'limite'):
            planejar_arquivo(self.origem, 'prova.pdf')

    def test_extensao_do_campo_e_revalidada(self):
        with self.assertRaisesMessage(ValidationError, 'Extensão'):
            planejar_arquivo(self.origem, 'prova.pdf', extensoes=['png'])
