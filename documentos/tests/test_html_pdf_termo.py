"""Caminho HTML → PDF do termo de autorização: as três variantes dos .docx de
origem em um template só, com lacuna onde o modelo impresso tem linha para
preencher à mão."""

import io
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase, override_settings

from documentos.services.document_context import contexto_de_payload
from documentos.services.pdf_renderer import caminhos_dos_templates, render_pdf, renderizar_html, weasyprint_disponivel
from documentos.services.types import DocumentoFormato, DocumentoTipo

TERMO = DocumentoTipo.TERMO_AUTORIZACAO
TX = {
    "unidade": "ASSESSORIA DE COMUNICAÇÃO SOCIAL", "unidade_rodape": "ASCOM - Rua X, 1 - Curitiba/PR",
    "nome_servidor": "MARIA DA SILVA", "rg_servidor": "12.345.678-9", "cpf_servidor": "123.456.789-00",
    "telefone": "(41) 99999-0000", "lotacao": "ASCOM", "data_do_evento": "no dia 10 de outubro de 2026",
    "destino": "Foz do Iguaçu/PR", "viatura": "Chevrolet Spin", "placa": "ABC-1D23", "combustivel": "Gasolina",
}


def _html(variante, tx=TX, modo="pdf"):
    return renderizar_html(TERMO, contexto_de_payload(TERMO, {"termo": {"variante": variante}}, tx, modo=modo), modo=modo)


class TemplateDoTermoTests(SimpleTestCase):
    def test_completo_com_viatura_preenche_servidor_e_viatura(self):
        html = _html("completo_com_viatura")
        for texto in ["ASSESSORIA DE COMUNICAÇÃO SOCIAL", "Termo de autorização para participação em eventos da ASCOM",
                      "Eu&nbsp;MARIA DA SILVA, CPF:&nbsp;123.456.789-00", "lotado(a) na(o)&nbsp;ASCOM", "<strong>no dia 10 de outubro de 2026</strong>",
                      "<strong>Foz do Iguaçu/PR</strong>", "<strong>Viatura:</strong> Chevrolet Spin", "ABC-1D23 / Gasolina", "cartão corporativo vigente",
                      "Autorização da Chefia", "ASCOM - Rua X, 1 - Curitiba/PR"]:
            self.assertIn(texto, html)
        self.assertNotIn("doc-lacuna", html)
        self.assertNotIn("RG:", html)  # o termo não pede mais o RG
        # Rodapé próprio: nada do destinatário do ofício.
        self.assertNotIn("Exmo. Sr", html)

    def test_sem_viatura_deixa_a_viatura_para_preencher(self):
        html = _html("completo_sem_viatura")
        self.assertIn("Eu&nbsp;MARIA DA SILVA", html)
        self.assertIn("<strong>Viatura:</strong> Modelo:", html)
        self.assertNotIn("Chevrolet Spin", html)

    def test_semipreenchido_so_traz_data_e_destino(self):
        html = _html("semipreenchido")
        self.assertNotIn("MARIA DA SILVA", html)
        self.assertNotIn("Chevrolet Spin", html)
        self.assertIn("no dia 10 de outubro de 2026", html)
        self.assertIn("Foz do Iguaçu/PR", html)
        self.assertGreaterEqual(html.count('class="doc-lacuna'), 6)
        self.assertNotIn("<span>RG</span>", html)

    def test_campo_sem_valor_vira_lacuna(self):
        html = _html("completo_com_viatura", dict(TX, nome_servidor="", telefone="-"))
        self.assertEqual(html.count("doc-lacuna--curta"), 2)
        self.assertNotIn("telefone -", html)
        self.assertIn('<span class="doc-junto">Eu <span class="doc-lacuna', html)  # rótulo e lacuna não se separam
        self.assertIn("doc-termo__texto--lacunas", html)  # sem justificar: não estica os espaços
        self.assertNotIn("doc-termo__texto--lacunas", _html("completo_com_viatura"))

    def test_termo_so_da_viatura_usa_as_linhas_do_semipreenchido(self):
        sem_servidor = dict(TX, nome_servidor="", cpf_servidor="", telefone="", lotacao="")
        html = _html("completo_com_viatura", sem_servidor)
        self.assertIn('<p class="doc-termo__preencher"><span>Eu</span>', html)
        self.assertNotIn("doc-lacuna--curta", html)
        self.assertIn("Chevrolet Spin", html)

    def test_css_do_termo_entra_na_tela_e_no_cache(self):
        self.assertIn("doc-termo", _html("completo_com_viatura", modo="editor").split("</style>")[0])
        self.assertIn("termo_autorizacao.css", [p.name for p in caminhos_dos_templates(TERMO)])


class FacadeDoTermoTests(TestCase):
    @override_settings(DOCUMENTOS_PERSIST_ARTEFATOS=False)
    def test_pdf_do_termo_nasce_do_html(self):
        from documentos.services.facade import DocumentoFacade

        with mock.patch("documentos.services.pdf_renderer.render_pdf", return_value=b"%PDF-1.7 fake"):
            payload = {"institucional": {}, "oficio": {}, "termo": {"variante": "semipreenchido"}}
            doc = DocumentoFacade().gerar(tipo=TERMO, formato=DocumentoFormato.PDF, payload=payload, docxtpl_context=TX, reference="t")
        self.assertEqual(doc.pdf_engine_used, "html_weasyprint")


@skipUnless(weasyprint_disponivel(), "WeasyPrint sem runtime nativo nesta máquina")
class PdfRealDoTermoTests(SimpleTestCase):
    def test_cada_variante_cabe_em_uma_pagina(self):
        from pypdf import PdfReader

        for variante in ("semipreenchido", "completo_com_viatura", "completo_sem_viatura"):
            with self.subTest(variante=variante):
                leitor = PdfReader(io.BytesIO(render_pdf(_html(variante), tipo=TERMO)))
                self.assertEqual(len(leitor.pages), 1)
                self.assertIn("POLÍCIA CIVIL DO PARANÁ", leitor.pages[0].extract_text())
