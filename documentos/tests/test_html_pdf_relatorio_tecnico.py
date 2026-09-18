"""Caminho HTML → PDF do Relatório Técnico de Viagem: o relatorio-tecnico.docx na
folha ASCOM, com o mesmo contexto que o DOCX recebe."""

import io
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase, override_settings

from documentos.services.document_context import contexto_de_payload
from documentos.services.pdf_renderer import caminhos_dos_templates, render_pdf, renderizar_html, weasyprint_disponivel
from documentos.services.types import DocumentoFormato, DocumentoTipo

RT = DocumentoTipo.RELATORIO_TECNICO
TX = {
    "oficio": "900011/2026", "sede": "Curitiba", "data_atual_extenso": "26 de setembro de 2026",
    "unidade_cabecalho": "ASSESSORIA DE COMUNICAÇÃO SOCIAL", "unidade_rodape": "Assessoria de Comunicação Social",
    "endereco": "Rua X, 1 - Curitiba/PR", "telefone": "(41) 3000-0000", "email": "ascom@pc.pr.gov.br",
    "nome_servidor": "MARIA DA SILVA", "cpf_servidor": "123.456.789-00", "diaria": "R$234,00", "translado": "Não houve",
    "combustivel": "", "passagem": "Não houve", "motivo": "Auditoria <b>prática</b>", "atividade": "Linha um\nLinha dois",
    "conclusao": "", "medidas": "", "info_complementares": "",
}


def _html(tx=TX, modo="pdf"):
    return renderizar_html(RT, contexto_de_payload(RT, tx, tx, modo=modo), modo=modo)


class TemplateDoRelatorioTests(SimpleTestCase):
    def test_reproduz_o_modelo(self):
        html = _html()
        for texto in ["ASSESSORIA DE COMUNICAÇÃO SOCIAL", "Ref. ao Ofício 900011/2026", "Curitiba, 26 de setembro de 2026",
                      "<th>Nome</th><td>MARIA DA SILVA</td>", "<th>CPF</th><td>123.456.789-00</td>", "<th>Diária:</th><td>R$234,00</td>",
                      "<th>Descrição do evento</th>", "Auditoria &lt;b&gt;prática&lt;/b&gt;", "Linha um<br>Linha dois",
                      "<th>Informações complementares</th>", "Declaramos que o trabalho previsto", "CPF 123.456.789-00",
                      "Assessoria de Comunicação Social - Rua X, 1 - Curitiba/PR (41) 3000-0000 – ascom@pc.pr.gov.br"]:
            self.assertIn(texto, html)
        self.assertEqual(html.count('<tbody class="doc-rt__secao">'), 5)

    def test_combustivel_vem_do_relatorio_e_cai_no_cartao_prime(self):
        self.assertIn("<th>Combustível:</th><td>Cartão Prime</td>", _html())
        self.assertIn("<th>Combustível:</th><td>Abastecimento na unidade</td>", _html(dict(TX, combustivel="Abastecimento na unidade")))

    def test_css_proprio_entra_no_cache(self):
        self.assertIn("relatorio_tecnico.css", [p.name for p in caminhos_dos_templates(RT)])


class FacadeDoRelatorioTests(TestCase):
    @override_settings(DOCUMENTOS_PERSIST_ARTEFATOS=False)
    def test_pdf_do_relatorio_nasce_do_html(self):
        from documentos.services.facade import DocumentoFacade

        with mock.patch("documentos.services.pdf_renderer.render_pdf", return_value=b"%PDF-1.7 fake"):
            doc = DocumentoFacade().gerar(tipo=RT, formato=DocumentoFormato.PDF, payload=TX, docxtpl_context=TX, reference="t")
        self.assertEqual(doc.pdf_engine_used, "html_weasyprint")


@skipUnless(weasyprint_disponivel(), "WeasyPrint sem runtime nativo nesta máquina")
class PdfRealDoRelatorioTests(SimpleTestCase):
    def test_uma_pagina_e_texto_longo_segue_para_a_seguinte(self):
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(render_pdf(_html(), tipo=RT)))
        self.assertEqual(len(leitor.pages), 1)
        self.assertIn("RELATÓRIO TÉCNICO DE VIAGEM", leitor.pages[0].extract_text())
        # Texto que estouraria a página no tamanho normal: o motor compacta e cabe numa só.
        frase = "Texto do relatório com uma frase de tamanho comum para medir. "
        medio = dict(TX, motivo=frase * 20, atividade=frase * 20, conclusao=frase * 20)
        self.assertEqual(len(PdfReader(io.BytesIO(render_pdf(_html(medio), tipo=RT))).pages), 1)
        longo = PdfReader(io.BytesIO(render_pdf(_html(dict(TX, conclusao="Texto longo da conclusão. " * 400)), tipo=RT)))
        self.assertGreater(len(longo.pages), 1)
        for pagina in longo.pages:
            self.assertIn("POLÍCIA CIVIL DO PARANÁ", pagina.extract_text())
