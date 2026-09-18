"""Caminho HTML → PDF da justificativa: o justificativa.docx na folha ASCOM,
com os mesmos textos que o DOCX recebe."""

import io
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase, override_settings

from documentos.services.document_context import contexto_de_payload
from documentos.services.pdf_renderer import caminhos_dos_templates, render_pdf, renderizar_html, weasyprint_disponivel
from documentos.services.types import DocumentoFormato, DocumentoTipo

JUSTIFICATIVA = DocumentoTipo.JUSTIFICATIVA
TX = {
    "unidade": "ASSESSORIA DE COMUNICAÇÃO SOCIAL", "unidade_rodape": "ASCOM - Rua X, 1 - Curitiba/PR",
    "sede": "Curitiba", "data_extenso": "18 de setembro de 2026",
    "justificativa": "Primeiro parágrafo <b>da</b> justificativa.\n\nSegundo parágrafo.",
    "assinante_justificativa": "Fulano de Tal", "cargo_assinante_justificativa": "Delegado de Polícia",
}


def _html(tx=TX, modo="pdf"):
    return renderizar_html(JUSTIFICATIVA, contexto_de_payload(JUSTIFICATIVA, {}, tx, modo=modo), modo=modo)


class TemplateDaJustificativaTests(SimpleTestCase):
    def test_reproduz_o_modelo_na_folha_ascom(self):
        html = _html()
        for texto in ["ASSESSORIA DE COMUNICAÇÃO SOCIAL", "Curitiba, 18 de setembro de 2026", ">Justificativa</h1>",
                      "Fulano de Tal", "Delegado de Polícia", "ASCOM - Rua X, 1 - Curitiba/PR", "doc-folha-ascom"]:
            self.assertIn(texto, html)
        self.assertNotIn("Exmo. Sr", html)

    def test_cada_linha_do_texto_e_um_paragrafo_escapado(self):
        html = _html()
        self.assertIn("<p>Primeiro parágrafo &lt;b&gt;da&lt;/b&gt; justificativa.</p><p>Segundo parágrafo.</p>", html)

    def test_sem_assinante_nao_deixa_bloco_vazio(self):
        html = _html(dict(TX, assinante_justificativa="", cargo_assinante_justificativa=""))
        self.assertNotIn("doc-justificativa__assinatura", html)

    def test_css_proprio_entra_no_cache(self):
        self.assertIn("justificativa.css", [p.name for p in caminhos_dos_templates(JUSTIFICATIVA)])


class FacadeDaJustificativaTests(TestCase):
    @override_settings(DOCUMENTOS_PERSIST_ARTEFATOS=False)
    def test_pdf_da_justificativa_nasce_do_html(self):
        from documentos.services.facade import DocumentoFacade

        payload = {"institucional": {}, "oficio": {}, "justificativa": {}}
        with mock.patch("documentos.services.pdf_renderer.render_pdf", return_value=b"%PDF-1.7 fake"):
            doc = DocumentoFacade().gerar(tipo=JUSTIFICATIVA, formato=DocumentoFormato.PDF, payload=payload, docxtpl_context=TX, reference="t")
        self.assertEqual(doc.pdf_engine_used, "html_weasyprint")


@skipUnless(weasyprint_disponivel(), "WeasyPrint sem runtime nativo nesta máquina")
class PdfRealDaJustificativaTests(SimpleTestCase):
    def test_uma_pagina_com_cabecalho_e_texto(self):
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(render_pdf(_html(), tipo=JUSTIFICATIVA)))
        self.assertEqual(len(leitor.pages), 1)
        texto = leitor.pages[0].extract_text()
        for trecho in ("POLÍCIA CIVIL DO PARANÁ", "JUSTIFICATIVA", "Segundo parágrafo", "Fulano de Tal"):
            self.assertIn(trecho, texto)
