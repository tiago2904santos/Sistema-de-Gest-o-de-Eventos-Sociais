"""Caminho HTML → PDF do Diário de Bordo: o diario_bordo.xlsx em A4 deitada, com
os mesmos dados que preenchem a planilha. A planilha (.xlsx) continua saindo
do modelo."""

import io
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase, override_settings

from documentos.services.document_context import contexto_de_payload
from documentos.services.pdf_renderer import caminhos_dos_templates, render_pdf, renderizar_html, weasyprint_disponivel
from documentos.services.types import DocumentoFormato, DocumentoTipo

DIARIO = DocumentoTipo.DIARIO_BORDO
HEADER = {
    "divisao": "DIVISÃO X", "unidade_cabecalho": "ASSESSORIA DE COMUNICAÇÃO SOCIAL", "oficio_motorista": "900011", "ano": "2026",
    "protocolo_motorista": "12.345.678-9", "viatura": "Spin <b>(Descaracterizada)</b>", "combustivel": "GASOLINA", "placa": "ZZE9T92",
    "placa_reservada": "", "motorista": "DEMAFE - AROLDO", "cpf_motorista": "123.456.789-00",
}
TRECHO = {
    "data_saida": "25/09/2026", "hora_saida": "08:00", "km_inicial": 123456, "data_chegada": "25/09/2026", "hora_chegada": "12:00",
    "km_final": 123700, "origem": "CURITIBA", "destino": "GUARAPUAVA", "abastecimento": "( X ) Sim   (   ) Não",
}
PAYLOAD = {"header": HEADER, "trechos": [TRECHO]}


def _html(payload=PAYLOAD, modo="pdf"):
    return renderizar_html(DIARIO, contexto_de_payload(DIARIO, payload, None, modo=modo), modo=modo)


class TemplateDoDiarioTests(SimpleTestCase):
    def test_reproduz_a_planilha(self):
        html = _html()
        for texto in ["DIVISÃO X", "ASSESSORIA DE COMUNICAÇÃO SOCIAL", "Referente ao Ofício: 900011/2026", "E-protocolo: 12.345.678-9",
                      "Spin &lt;b&gt;(Descaracterizada)&lt;/b&gt;", "Placa oficial: ZZE9T92", "<td>123456</td>", "<td>123700</td>",
                      "<td colspan=\"2\">GUARAPUAVA</td>", "( X ) Sim   (   ) Não", "Nome: DEMAFE - AROLDO", "CPF: 123.456.789-00"]:
            self.assertIn(texto, html)
        # O diário não tem rodapé: nenhuma linha de texto nele (a marca é escondida pelo CSS do tipo).
        for classe in ("doc-rodape__unidade", "doc-rodape__endereco", "doc-rodape__linha"):
            self.assertNotIn(classe, html)

    def test_sem_trechos_deixa_uma_linha_em_branco(self):
        html = _html({"header": HEADER, "trechos": []})
        self.assertIn('<td colspan="2"></td>', html)

    def test_css_proprio_entra_no_cache(self):
        self.assertIn("diario_bordo.css", [p.name for p in caminhos_dos_templates(DIARIO)])


class FacadeDoDiarioTests(TestCase):
    @override_settings(DOCUMENTOS_PERSIST_ARTEFATOS=False)
    def test_pdf_nasce_do_html_e_a_planilha_continua_do_modelo(self):
        from documentos.services.facade import DocumentoFacade

        with mock.patch("documentos.services.pdf_renderer.render_pdf", return_value=b"%PDF-1.7 fake"):
            pdf = DocumentoFacade().gerar(tipo=DIARIO, formato=DocumentoFormato.PDF, payload=PAYLOAD, reference="t")
        self.assertEqual(pdf.pdf_engine_used, "html_weasyprint")
        planilha = DocumentoFacade().gerar(tipo=DIARIO, formato=DocumentoFormato.XLSX, payload=PAYLOAD, reference="t")
        self.assertTrue(planilha.conteudo.startswith(b"PK"))


@skipUnless(weasyprint_disponivel(), "WeasyPrint sem runtime nativo nesta máquina")
class PdfRealDoDiarioTests(SimpleTestCase):
    def test_pagina_deitada_e_cabecalho_da_tabela_repetido(self):
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(render_pdf(_html(), tipo=DIARIO)))
        pagina = leitor.pages[0]
        self.assertGreater(float(pagina.mediabox.width), float(pagina.mediabox.height))  # A4 deitada
        longo = PdfReader(io.BytesIO(render_pdf(_html({"header": HEADER, "trechos": [TRECHO] * 30}), tipo=DIARIO)))
        self.assertGreater(len(longo.pages), 1)
        for pagina in longo.pages:
            texto = pagina.extract_text()
            self.assertIn("POLÍCIA CIVIL DO PARANÁ", texto)
            self.assertIn("KM (inicial)", texto)
        self.assertIn("Nome: DEMAFE - AROLDO", longo.pages[-1].extract_text())
