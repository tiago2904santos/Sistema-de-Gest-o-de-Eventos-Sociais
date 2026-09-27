"""PDF de arquivo (m126): PDF/A com metadados, fontes embutidas e marcação
de estrutura para leitores de tela."""

import io
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from documentos.services.document_context import contexto_de_payload, metadados_do_documento
from documentos.services.pdf_renderer import opcoes_do_pdf, render_pdf, renderizar_html, weasyprint_disponivel
from documentos.services.types import DocumentoTipo
from documentos.tests.test_html_pdf_oficio import PAYLOAD, TX


class MetadadosEOpcoesTests(SimpleTestCase):
    def test_metadados_institucionais_no_contexto_e_na_folha(self):
        contexto = contexto_de_payload(DocumentoTipo.OFICIO, PAYLOAD, TX, modo="pdf")
        self.assertEqual(contexto["metadados"]["autor"], "ASSESSORIA DE COMUNICAÇÃO – POLÍCIA CIVIL DO PARANÁ")
        self.assertEqual(contexto["metadados"]["assunto"], "Ofício – ASSESSORIA DE COMUNICAÇÃO – POLÍCIA CIVIL DO PARANÁ")
        self.assertIn("Ofício, ASSESSORIA DE COMUNICAÇÃO", contexto["metadados"]["palavras_chave"])
        html = renderizar_html(DocumentoTipo.OFICIO, contexto, modo="pdf")
        self.assertIn('<meta name="author" content="ASSESSORIA DE COMUNICAÇÃO – POLÍCIA CIVIL DO PARANÁ">', html)
        self.assertIn('<meta name="description" content="Ofício – ', html)
        self.assertIn('<meta name="keywords"', html)

    def test_metadados_sem_unidade_usam_o_orgao(self):
        dados = metadados_do_documento(DocumentoTipo.ORDEM_SERVICO, {"institucional": {}})
        self.assertEqual(dados["autor"], "POLÍCIA CIVIL DO PARANÁ")
        self.assertEqual(dados["assunto"], "Ordem de serviço – POLÍCIA CIVIL DO PARANÁ")

    def test_opcoes_padrao_e_desligavel(self):
        self.assertEqual(opcoes_do_pdf(), {"pdf_tags": True, "pdf_variant": "pdf/a-2a"})
        with override_settings(DOCUMENTOS_PDF_VARIANTE=""):
            self.assertEqual(opcoes_do_pdf(), {"pdf_tags": True})

    def test_fontes_proprias_no_repositorio_e_nos_css(self):
        pasta = Path(settings.BASE_DIR) / "static" / "fonts"
        for nome in ("LiberationSerif-Regular", "LiberationSerif-Bold", "LiberationSans-Regular", "LiberationSans-Bold"):
            self.assertTrue((pasta / f"{nome}.ttf").is_file(), nome)
        self.assertTrue((pasta / "LICENSE-Liberation.txt").is_file())
        impressao = (Path(settings.BASE_DIR) / "templates/documentos/pdf/documento-impressao.css").read_text(encoding="utf-8")
        self.assertIn('@font-face { font-family: "Liberation Serif"', impressao)
        self.assertIn("../../../static/fonts/LiberationSerif-Regular.ttf", impressao)
        editor = (Path(settings.BASE_DIR) / "templates/documentos/pdf/documento-editor.css").read_text(encoding="utf-8")
        self.assertIn("/static/fonts/LiberationSerif-Regular.ttf", editor)


@skipUnless(weasyprint_disponivel(), "WeasyPrint sem runtime nativo nesta máquina")
class PdfAReal(SimpleTestCase):
    def _pdf(self):
        return render_pdf(renderizar_html(DocumentoTipo.OFICIO, contexto_de_payload(DocumentoTipo.OFICIO, PAYLOAD, TX, modo="pdf"), modo="pdf"), tipo=DocumentoTipo.OFICIO)

    def test_pdf_a_com_metadados_marcacao_e_fontes_embutidas(self):
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(self._pdf()))
        xmp = leitor.xmp_metadata.stream.get_data().decode("utf-8")
        self.assertIn("pdfaid:part", xmp)
        raiz = leitor.trailer["/Root"]
        self.assertIn("/StructTreeRoot", raiz)
        self.assertTrue(raiz["/MarkInfo"]["/Marked"])
        self.assertEqual(leitor.metadata["/Author"], "ASSESSORIA DE COMUNICAÇÃO – POLÍCIA CIVIL DO PARANÁ")
        self.assertIn("Ofício", leitor.metadata["/Subject"])
        self.assertIn("Polícia Civil do Paraná", leitor.metadata["/Keywords"])
        self.assertEqual(leitor.metadata["/Title"], "Ofício 023/2026")
        fontes = set()
        for pagina in leitor.pages:
            for fonte in (pagina["/Resources"].get("/Font") or {}).values():
                fonte = fonte.get_object()
                descritor = fonte.get("/FontDescriptor")
                if descritor is None and "/DescendantFonts" in fonte:
                    descritor = fonte["/DescendantFonts"][0].get_object().get("/FontDescriptor")
                descritor = descritor.get_object() if descritor is not None else {}
                fontes.add((str(fonte.get("/BaseFont")), "/FontFile2" in descritor or "/FontFile3" in descritor or "/FontFile" in descritor))
        self.assertTrue(fontes)
        self.assertTrue(all(embutida for _, embutida in fontes), fontes)
        self.assertTrue(any("Liberation" in nome for nome, _ in fontes), fontes)

    def test_sem_variante_sai_pdf_comum(self):
        from pypdf import PdfReader

        with override_settings(DOCUMENTOS_PDF_VARIANTE=""):
            leitor = PdfReader(io.BytesIO(self._pdf()))
        self.assertTrue(leitor.xmp_metadata is None or "pdfaid:part" not in leitor.xmp_metadata.stream.get_data().decode("utf-8"))
