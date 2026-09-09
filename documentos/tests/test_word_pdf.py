from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from documentos.services.adapters import word_pdf as wp


class WordPdfAvailabilityTests(SimpleTestCase):
    def test_nao_windows_retorna_false(self):
        with mock.patch.object(wp.platform, "system", return_value="Linux"):
            self.assertFalse(wp.is_word_pdf_available())

    @mock.patch.object(wp.platform, "system", return_value="Windows")
    def test_sonda_nao_abre_o_word(self, _m):
        """A sonda lê o registro; abrir o Word custava 4,5 s no primeiro uso.

        Ela roda no caminho crítico da geração — a cadeia de motores entra na
        chave de cache do documento.
        """
        with mock.patch.object(wp.importlib.util, "find_spec", return_value=object()):
            with mock.patch.object(wp, "word_progid_registrado", return_value=True) as progid:
                self.assertTrue(wp.is_word_pdf_available())
        progid.assert_called_once()

    @mock.patch.object(wp.platform, "system", return_value="Windows")
    def test_sem_pywin32_retorna_false(self, _m):
        with mock.patch.object(wp.importlib.util, "find_spec", return_value=None):
            with mock.patch.object(wp, "word_progid_registrado") as progid:
                self.assertFalse(wp.is_word_pdf_available())
        progid.assert_not_called()

    @mock.patch.object(wp.platform, "system", return_value="Windows")
    def test_word_nao_registrado_retorna_false(self, _m):
        with mock.patch.object(wp.importlib.util, "find_spec", return_value=object()):
            with mock.patch.object(wp, "word_progid_registrado", return_value=False):
                self.assertFalse(wp.is_word_pdf_available())

class WordPdfConvertTests(SimpleTestCase):
    def test_fora_do_windows_erro(self):
        with mock.patch.object(wp.platform, "system", return_value="Darwin"):
            with self.assertRaises(OSError):
                wp.convert_docx_to_pdf_word_com(b"%PDF-fake-docx")

    @mock.patch.object(wp.platform, "system", return_value="Windows")
    def test_docx2pdf_converte(self, *_m):
        def fake_convert(src, dst):
            Path(dst).write_bytes(b"%PDF-ok")

        fake_mod = mock.Mock(convert=fake_convert)
        with mock.patch.dict("sys.modules", {"docx2pdf": fake_mod}):
            out = wp.convert_docx_to_pdf_word_com(b"PK\x03\x04fake")
        self.assertEqual(out, b"%PDF-ok")

    @mock.patch.object(wp.platform, "system", return_value="Windows")
    def test_docx2pdf_falha_propaga_mensagem_amigavel(self, *_m):
        fake_mod = mock.Mock(convert=mock.Mock(side_effect=RuntimeError("x")))
        with mock.patch.dict("sys.modules", {"docx2pdf": fake_mod}):
            with self.assertRaises(RuntimeError) as ctx:
                wp.convert_docx_to_pdf_word_com(b"x")
        self.assertIn("Microsoft Word", str(ctx.exception))
