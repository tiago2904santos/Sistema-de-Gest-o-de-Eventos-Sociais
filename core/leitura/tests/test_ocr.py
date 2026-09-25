"""OCR opcional: com o tesseract de verdade (se instalado) e com o subprocess simulado."""

import shutil
import subprocess
from unittest import mock
from unittest import skipUnless

from django.test import SimpleTestCase
from django.test import override_settings

from core.leitura import ocr
from core.leitura.tests import fabrica as f

TEM_TESSERACT = bool(shutil.which("tesseract"))

_OSD_90 = b"Page number: 0\nOrientation in degrees: 270\nRotate: 90\nOrientation confidence: 9.50\nScript: Latin\n"


def _tsv(*linhas):
    """Saída TSV do tesseract com uma palavra por item: (texto, confiança, largura, altura)."""
    cabecalho = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    corpo = [
        f"5\t1\t1\t1\t{n}\t1\t10\t{10 * n}\t{largura}\t{altura}\t{conf}\t{palavra}"
        for n, (palavra, conf, largura, altura) in enumerate(linhas, start=1)
    ]
    return ("\n".join([cabecalho, *corpo]) + "\n").encode()


class _Resposta:
    def __init__(self, stdout=b"", returncode=0):
        self.stdout = stdout
        self.stderr = b""
        self.returncode = returncode


@override_settings(OCR_ATIVO=True, TESSERACT_CMD="/opt/ocr/tesseract", OCR_TIMEOUT=7, OCR_DPI=72)
class OcrSimuladoTests(SimpleTestCase):
    def setUp(self):
        self.pdf = f.pagina_imagem(f.comprovante())
        patcher = mock.patch("core.leitura.ocr.shutil.which", return_value="/opt/ocr/tesseract")
        self.which = patcher.start()
        self.addCleanup(patcher.stop)

    def test_disponivel_depende_do_binario_e_do_ajuste(self):
        self.assertTrue(ocr.disponivel())
        self.which.assert_called_with("/opt/ocr/tesseract")
        self.which.return_value = None
        self.assertFalse(ocr.disponivel())
        self.which.return_value = "/opt/ocr/tesseract"
        with override_settings(OCR_ATIVO=False):
            self.assertFalse(ocr.disponivel())

    def test_chama_o_tesseract_com_uma_thread_e_timeout(self):
        boa = _tsv(("COMPROVANTE", 95, 200, 20), ("SAQUE", 91, 90, 20))
        lixo = _tsv(("3VQAS", 30, 90, 20))
        with mock.patch("core.leitura.ocr.subprocess.run", side_effect=[_Resposta(_OSD_90), _Resposta(boa), _Resposta(lixo)]) as run:
            leitura = ocr.analisar_pagina(self.pdf, 0)
        # Leitura curta: mesmo com o OSD confiante, o sentido oposto é conferido.
        self.assertEqual(run.call_count, 3)
        self.assertEqual(leitura.rotacao, 90)
        self.assertEqual(leitura.texto, "COMPROVANTE\nSAQUE")
        for chamada in run.call_args_list:
            argumentos, opcoes = chamada
            self.assertEqual(argumentos[0][:3], ["/opt/ocr/tesseract", "stdin", "stdout"])
            self.assertEqual(opcoes["env"]["OMP_THREAD_LIMIT"], "1")
            self.assertEqual(opcoes["timeout"], 7.0)
            self.assertTrue(opcoes["input"].startswith(b"\x89PNG"))
        self.assertEqual(run.call_args_list[0][0][0][3:5], ["--psm", "0"])  # orientação
        self.assertIn("tsv", run.call_args_list[1][0][0])

    def test_osd_fraco_e_conferido_pela_leitura_no_sentido_oposto(self):
        """OSD diz 180 com confiança baixa; a leitura a 0 sai boa e a 180 sai lixo: vale 0."""
        osd = b"Rotate: 180\nOrientation confidence: 1.20\n"
        lixo = _tsv(("00'0Z", 20, 60, 20))
        boa = _tsv(("BANCO", 96, 120, 20), ("BRASIL", 95, 130, 20), ("COMPROVANTE", 94, 250, 20), ("SAQUE", 93, 110, 20))
        with mock.patch("core.leitura.ocr.subprocess.run", side_effect=[_Resposta(osd), _Resposta(lixo), _Resposta(boa)]):
            leitura = ocr.analisar_pagina(self.pdf, 0)
        self.assertEqual(leitura.rotacao, 0)
        self.assertIn("COMPROVANTE", leitura.texto)

    def test_palavra_de_caixa_alta_nao_conta_como_texto_em_pe(self):
        deitada = _tsv(*[("COMPROVANTE", 95, 20, 200)] * 6)
        with mock.patch("core.leitura.ocr.subprocess.run", side_effect=[_Resposta(_OSD_90), _Resposta(deitada), _Resposta(deitada)]):
            leitura = ocr.analisar_pagina(self.pdf, 0)
        self.assertIsNone(leitura.rotacao)

    def test_timeout_e_erro_viram_resposta_vazia_sem_texto_no_log(self):
        with mock.patch("core.leitura.ocr.subprocess.run", side_effect=subprocess.TimeoutExpired("tesseract", 7)), \
                self.assertLogs("core.errors", level="WARNING") as registro:
            self.assertIsNone(ocr.orientacao_da_pagina(self.pdf, 0))
            self.assertEqual(ocr.texto_da_pagina(self.pdf, 0), "")
        self.assertTrue(all("leitura.ocr" in linha for linha in registro.output))
        with mock.patch("core.leitura.ocr.subprocess.run", return_value=_Resposta(b"FULANO 123.456.789-09", returncode=1)), \
                self.assertLogs("core.leitura.ocr", level="WARNING") as registro:
            self.assertEqual(ocr.texto_da_pagina(self.pdf, 0, rotacao=0), "")
        self.assertNotIn("FULANO", " ".join(registro.output))

    def test_sem_o_idioma_tenta_sem_ele(self):
        respostas = [_Resposta(b"", returncode=1), _Resposta(_tsv(("VALOR", 90, 100, 20)))]
        with mock.patch("core.leitura.ocr.subprocess.run", side_effect=respostas) as run, \
                self.assertLogs("core.leitura.ocr", level="WARNING"):
            self.assertEqual(ocr.texto_da_pagina(self.pdf, 0, rotacao=0), "VALOR")
        self.assertIn("-l", run.call_args_list[0][0][0])
        self.assertNotIn("-l", run.call_args_list[1][0][0])

    def test_sem_binario_nao_chama_nada(self):
        self.which.return_value = None
        with mock.patch("core.leitura.ocr.subprocess.run") as run:
            self.assertEqual(ocr.analisar_pagina(self.pdf, 0).texto, "")
        run.assert_not_called()


@skipUnless(TEM_TESSERACT, "tesseract não instalado")
@override_settings(OCR_ATIVO=True, TESSERACT_CMD="", OCR_DPI=150)
class OcrDeVerdadeTests(SimpleTestCase):
    def test_orientacao_e_texto_de_comprovante_fotografado(self):
        cpf = f.gerar_cpf(5)
        for girar, esperado in ((0, 0), (90, 270), (180, 180), (270, 90)):
            with self.subTest(girar=girar):
                pdf = f.pagina_imagem(f.comprovante("bb_saque", nome="JOANA DA SILVA PEREIRA", cpf=cpf, valor="321,00"), girar=girar)
                leitura = ocr.analisar_pagina(pdf, 0)
                self.assertEqual(leitura.rotacao, esperado)
                self.assertIn("SAQUE", leitura.texto.upper())
                self.assertIn("321,00", leitura.texto)

    def test_diario_escaneado_deitado(self):
        pdf = f.pagina_imagem(f.diario_bordo(), girar=90)
        self.assertEqual(ocr.orientacao_da_pagina(pdf, 0), 270)
