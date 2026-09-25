"""Orientação pela matriz completa, recorte e conversão de imagem.

Os casos de orientação são os do experimento com as amostras reais: a
direção que o método dá é conferida pelo que o `extract_text(orientations)`
do pypdf daria (que erra na página embrulhada) e, nos casos principais,
desenhando a página corrigida com o pdfium e comparando com a referência em
pé.
"""

import io
import time
from unittest import mock

from django.test import SimpleTestCase
from django.test import override_settings
from pypdf import PdfReader

from core.leitura import pdf as leitura_pdf
from core.leitura.pdf import ler_paginas
from core.leitura.pdf import normalizar_orientacao
from core.leitura.pdf import recortar
from core.leitura.pdf import rotacao_para_ficar_em_pe
from core.leitura.tests import fabrica as f


def _ingenuo(dados):
    """Direção que o extract_text(orientations=…) do pypdf daria (o método que NÃO se usa)."""
    pagina = PdfReader(io.BytesIO(dados)).pages[0]
    contagem = {o: len("".join(pagina.extract_text(orientations=(o,)).split())) for o in (0, 90, 180, 270)}
    return max(contagem, key=contagem.get)


def _uma(dados):
    return ler_paginas(dados)[0]


@override_settings(OCR_ATIVO=False)
class OrientacaoTests(SimpleTestCase):
    """O /Rotate que deixa a página em pé, em cada situação que aparece de verdade."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.diario = f.diario_bordo()  # A4 deitado, em pé
        cls.referencia = f.imagem_da_pagina(cls.diario, dpi=40)

    def _conferir_visual(self, dados, rotacao):
        """Desenha a página com o /Rotate calculado e compara com o diário em pé."""
        corrigido = recortar(dados, [0], {0: rotacao})
        imagem = f.imagem_da_pagina(corrigido, dpi=40)
        oposto = f.imagem_da_pagina(recortar(dados, [0], {0: (rotacao + 180) % 360}), dpi=40)
        self.assertGreater(f.semelhanca(imagem, self.referencia), 0.9)
        self.assertLess(f.semelhanca(oposto, self.referencia), 0.2)

    def test_paisagem_em_pe_nao_gira(self):
        pagina = _uma(self.diario)
        self.assertEqual(pagina.angulo_texto, 0)
        self.assertEqual(rotacao_para_ficar_em_pe(pagina), 0)
        self.assertTrue(pagina.em_paisagem)

    def test_rotate_previo_e_desfeito(self):
        for graus in (90, 270):
            with self.subTest(graus=graus):
                dados = f.com_rotate(self.diario, graus)
                pagina = _uma(dados)
                self.assertEqual(pagina.rotacao, graus)
                self.assertEqual(rotacao_para_ficar_em_pe(pagina), 0)
                self._conferir_visual(dados, 0)

    def test_retrato_com_conteudo_a_90_e_a_270_distingue_o_sentido(self):
        deitado_horario = f.girar_conteudo(self.diario, 90)  # linhas descendo: conteúdo a 270°
        deitado_anti = f.girar_conteudo(self.diario, 270)  # linhas subindo: conteúdo a 90°
        self.assertEqual(rotacao_para_ficar_em_pe(_uma(deitado_horario)), 270)
        self.assertEqual(rotacao_para_ficar_em_pe(_uma(deitado_anti)), 90)
        self._conferir_visual(deitado_horario, 270)
        self._conferir_visual(deitado_anti, 90)

    def test_de_cabeca_para_baixo(self):
        dados = f.girar_conteudo(self.diario, 180)
        self.assertEqual(rotacao_para_ficar_em_pe(_uma(dados)), 180)
        self._conferir_visual(dados, 180)

    def test_conteudo_girado_mais_rotate_previo(self):
        dados = f.com_rotate(f.girar_conteudo(self.diario, 90), 90)
        self.assertEqual(rotacao_para_ficar_em_pe(_uma(dados)), 270)

    def test_form_com_matrix_que_gira_o_conteudo(self):
        """Só a /Matrix do form deita o diário: o pypdf a ignora e diria "em pé"."""
        dados = f.em_form(self.diario, (0, 1, -1, 0, 595.2756, 0), (595.2756, 841.8898))
        self.assertEqual(_ingenuo(dados), 0)
        pagina = _uma(dados)
        self.assertFalse(pagina.em_paisagem)
        self.assertEqual(rotacao_para_ficar_em_pe(pagina), 90)
        self._conferir_visual(dados, 90)

    def test_pagina_embrulhada_em_pe_nao_gira(self):
        """O eProtocolo embrulha a página num form com Y invertido: o pypdf ingênuo diria 180."""
        dados = f.emoldurar(f.oficio_viagens(), fls="2", mov="2", embrulhar=True)
        self.assertEqual(_ingenuo(dados), 180)
        pagina = _uma(dados)
        self.assertEqual(pagina.angulo_texto, 0)
        self.assertEqual(rotacao_para_ficar_em_pe(pagina), 0)

    def test_diario_paisagem_em_pe_embrulhado(self):
        dados = f.emoldurar(self.diario, fls="5", mov="3", embrulhar=True)
        self.assertEqual(_ingenuo(dados), 180)
        self.assertEqual(rotacao_para_ficar_em_pe(_uma(dados)), 0)

    def test_diario_deitado_embrulhado_na_moldura_retrato(self):
        """A moldura (rodapé e carimbo, sempre a 0°) não vota: o diário deitado manda."""
        for graus, esperado in ((90, 270), (270, 90)):
            with self.subTest(graus=graus):
                dados = f.emoldurar(f.girar_conteudo(self.diario, graus), fls="5", mov="3", embrulhar=True)
                pagina = _uma(dados)
                self.assertEqual(pagina.base, -40)
                self.assertEqual(rotacao_para_ficar_em_pe(pagina), esperado)
                self.assertTrue(leitura_pdf.fica_em_paisagem(pagina, esperado))

    def test_documento_aninhado_em_pe(self):
        antigo = f.emoldurar(f.oficio_viagens(), fls="240", mov="61", protocolo="24.740.746-4")
        dados = f.emoldurar(antigo, fls="2", mov="2", embrulhar=True)
        pagina = _uma(dados)
        self.assertEqual(pagina.base, -80)
        self.assertEqual(rotacao_para_ficar_em_pe(pagina), 0)

    def test_pagina_so_imagem_sem_ocr_nao_sabe(self):
        pagina = _uma(f.pagina_imagem(f.comprovante()))
        self.assertTrue(pagina.sem_texto)
        self.assertGreater(pagina.cobertura_imagem, 0.9)
        self.assertIsNone(pagina.angulo_texto)
        self.assertIsNone(rotacao_para_ficar_em_pe(pagina))


@override_settings(OCR_ATIVO=False)
class MolduraTests(SimpleTestCase):
    def test_corpo_sem_moldura_e_folha_de_assinatura(self):
        cpf = f.gerar_cpf(1)
        dados = f.emoldurar(f.relatorio_tecnico(cpf=cpf), fls="5", mov="4", assinantes=[("Fulano de Tal", cpf)])
        pagina = _uma(dados)
        self.assertIn("Relatório técnico de viagem", pagina.corpo)
        self.assertNotIn("Inserido ao protocolo", pagina.corpo)
        self.assertIn("Inserido ao protocolo", pagina.texto)
        self.assertFalse(pagina.sem_texto)

        folha = _uma(f.folha_assinatura(fls="5a", mov="4", arquivo="RT.pdf", assinantes=[("Fulano de Tal", cpf)]))
        self.assertEqual(folha.corpo, "")
        self.assertFalse(folha.sem_texto)  # é moldura, não escaneado

    def test_escaneado_com_moldura_e_sem_texto(self):
        pagina = _uma(f.emoldurar(f.pagina_imagem(f.certidao("MUNICIPAL")), fls="9", mov="9", embrulhar=True))
        self.assertTrue(pagina.sem_texto)
        self.assertEqual(pagina.corpo, "")


@override_settings(OCR_ATIVO=False)
class RecorteTests(SimpleTestCase):
    def test_recorta_na_ordem_com_rotate_normalizado_e_sem_metadados(self):
        processo = f.processo_eprotocolo([f.Doc(f.relatorio_tecnico(), arquivo="RT.pdf"), f.Doc(f.diario_bordo(), arquivo="DB.pdf")])
        saida = recortar(processo, [2, 1], {2: 450, 1: -90})
        leitor = PdfReader(io.BytesIO(saida))
        self.assertEqual(len(leitor.pages), 2)
        self.assertIn("Ficha individual", leitor.pages[0].extract_text())
        self.assertEqual(leitor.pages[0].get("/Rotate"), 90)
        self.assertEqual(leitor.pages[1].get("/Rotate"), 270)
        self.assertNotIn("/Author", leitor.metadata or {})
        self.assertFalse(leitor.outline)

    def test_indice_fora_do_pdf(self):
        with self.assertRaises(IndexError):
            recortar(f.pagina(["x"]), [3])

    def test_normalizar_orientacao(self):
        entrada = f.juntar(f.girar_conteudo(f.diario_bordo(), 90), f.oficio_viagens(), f.com_rotate(f.diario_bordo(), 270))
        saida, rotacoes = normalizar_orientacao(entrada)
        self.assertEqual(rotacoes, [270, 0, 0])
        paginas = ler_paginas(saida)
        self.assertEqual([p.rotacao for p in paginas], [270, 0, 0])
        self.assertTrue(paginas[0].em_paisagem)
        self.assertTrue(paginas[2].em_paisagem)

    def test_normalizar_sem_mudanca_devolve_os_mesmos_bytes(self):
        entrada = f.oficio_viagens()
        saida, rotacoes = normalizar_orientacao(entrada)
        self.assertIs(saida, entrada)
        self.assertEqual(rotacoes, [0])

    def test_imagem_sem_ocr_fica_paisagem_so_se_exigido_e_marca_incerta(self):
        escaneado = f.pagina_imagem(f.diario_bordo(), girar=90)  # retrato
        saida, rotacoes = normalizar_orientacao(escaneado)
        self.assertEqual(rotacoes, [None])
        self.assertIs(saida, escaneado)
        saida, rotacoes = normalizar_orientacao(escaneado, exigir_paisagem=True)
        self.assertEqual(rotacoes, [None])
        self.assertTrue(ler_paginas(saida)[0].em_paisagem)

    def test_imagem_usa_o_ocr_quando_ha(self):
        escaneado = f.pagina_imagem(f.diario_bordo(), girar=90)
        with mock.patch("core.leitura.ocr.disponivel", return_value=True), mock.patch(
            "core.leitura.ocr.orientacao_da_pagina", return_value=270
        ) as orientacao:
            saida, rotacoes = normalizar_orientacao(escaneado, exigir_paisagem=True)
        orientacao.assert_called_once()
        self.assertEqual(rotacoes, [270])
        self.assertEqual(ler_paginas(saida)[0].rotacao, 270)

    @override_settings(OCR_MAX_PAGINAS=1)
    def test_limite_de_paginas_do_ocr(self):
        escaneados = f.juntar(*(f.pagina_imagem(f.comprovante()) for _ in range(3)))
        with mock.patch("core.leitura.ocr.disponivel", return_value=True), mock.patch(
            "core.leitura.ocr.orientacao_da_pagina", return_value=0
        ) as orientacao:
            _, rotacoes = normalizar_orientacao(escaneados)
        self.assertEqual(orientacao.call_count, 1)
        self.assertEqual(rotacoes, [0, None, None])


class ImagemTests(SimpleTestCase):
    def _png(self, modo="RGBA", tamanho=(40, 30)):
        from PIL import Image

        saida = io.BytesIO()
        Image.new(modo, tamanho, (255, 0, 0, 128) if modo == "RGBA" else "red").save(saida, format="PNG")
        return saida.getvalue()

    def test_imagem_vira_pdf_de_uma_pagina(self):
        dados = leitura_pdf.imagem_para_pdf(self._png())
        self.assertTrue(dados.startswith(b"%PDF"))
        self.assertEqual(len(PdfReader(io.BytesIO(dados)).pages), 1)

    def test_conversor_antigo_da_prestacao_usa_o_novo(self):
        from viagens_prestacoes.services import _image_bytes_to_pdf

        png = self._png()
        self.assertEqual(len(PdfReader(io.BytesIO(_image_bytes_to_pdf(png))).pages), 1)
        with mock.patch("core.leitura.pdf.imagem_para_pdf", side_effect=leitura_pdf.ImagemInvalida("x")):
            from documentos.services.exceptions import DocumentValidationError

            with self.assertRaises(DocumentValidationError):
                _image_bytes_to_pdf(png)

    def test_como_pdf_desvira_foto_pela_exif(self):
        from PIL import Image

        imagem = Image.new("RGB", (60, 20), "white")
        exif = imagem.getexif()
        exif[0x0112] = 6  # câmera deitada: mostrar girando 90° no sentido horário
        saida = io.BytesIO()
        imagem.save(saida, format="JPEG", exif=exif.tobytes())
        pagina = PdfReader(io.BytesIO(leitura_pdf.como_pdf(saida.getvalue()))).pages[0]
        self.assertLess(float(pagina.mediabox.width), float(pagina.mediabox.height))

    def test_arquivo_que_nao_e_pdf_nem_imagem(self):
        with self.assertRaises(leitura_pdf.ArquivoIlegivel):
            ler_paginas(b"texto qualquer")
        with self.assertRaises(leitura_pdf.ArquivoIlegivel), self.assertLogs("pypdf", level="WARNING"):
            ler_paginas(b"%PDF-1.4 quebrado")


@override_settings(OCR_ATIVO=False)
class DesempenhoTests(SimpleTestCase):
    def test_volume_de_35_paginas_em_poucos_segundos(self):
        docs = [f.Doc(f.oficio_viagens(), arquivo="Of.pdf", assinantes=[("Chefe da Silva", f.gerar_cpf(2))], embrulhar=True)]
        docs += [f.Doc(f.contrato(paginas_=12), arquivo="Contrato.pdf", aninhado=True)]
        docs += [f.Doc(f.relatorio_tecnico(), arquivo=f"RT{i}.pdf", embrulhar=True) for i in range(9)]
        docs += [f.Doc(f.girar_conteudo(f.diario_bordo(), 90), arquivo="DB.pdf", embrulhar=True)]
        docs += [f.Doc(f.comprovante(m), arquivo=f"{m}.pdf") for m in list(f.MODELOS_COMPROVANTE)[:10]]
        dados = f.processo_eprotocolo(docs)
        self.assertGreaterEqual(len(PdfReader(io.BytesIO(dados)).pages), 35)
        from core.leitura.eprotocolo import ler_processo

        inicio = time.perf_counter()
        processo = ler_processo(dados)
        decorrido = time.perf_counter() - inicio
        self.assertEqual(len(processo.documentos), len(docs) + 1)
        self.assertLess(decorrido, 5.0)
