"""Caminho HTML → PDF da Ordem de Serviço: os dois .docx de origem (tipo padrão
e demais tipos) em um template só, na folha ASCOM."""

import io
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase, override_settings

from documentos.services.document_context import contexto_de_payload
from documentos.services.pdf_renderer import caminhos_dos_templates, render_pdf, renderizar_html, weasyprint_disponivel
from documentos.services.types import DocumentoFormato, DocumentoTipo

OS = DocumentoTipo.ORDEM_SERVICO
TX = {
    "ordem_de_servico": "002/2026", "unidade_abreviado": "ASCOM", "unidade": "ASSESSORIA DE COMUNICAÇÃO SOCIAL",
    "unidade_rodape": "Assessoria de Comunicação Social", "endereco": "Rua X, 1 - Curitiba/PR", "telefone": "(41) 3000-0000",
    "email": "ascom@pc.pr.gov.br", "nome_chefia": "Fulano de Tal", "cargo_chefia": "Delegado de Polícia",
    "equipe_deslocamento": "dos motoristas Leonardo e Aroldo", "destino": "Guarapuava/PR",
    "data_extenso": "nos dias 25 a 26 de setembro de 2026", "motivo": "Cobertura <b>do</b> evento",
    "tipo_necessidade": "PADRAO", "referencia": "Deslocamento - Caminhão", "determinacao": "O deslocamento da equipe abaixo relacionada:",
    "competencias_equipe": ["Leonardo: condução do caminhão", ""], "justificativas": ["Justificativa um.", "Justificativa dois."],
    "finalidade": "A presente Ordem de Serviço tem por finalidade garantir a atividade.",
    "sede": "Curitiba", "data_atual_extenso": "18 de setembro de 2026",
}


def _html(tx=TX, modo="pdf"):
    return renderizar_html(OS, contexto_de_payload(OS, {}, tx, modo=modo), modo=modo)


class TemplateDaOrdemTests(SimpleTestCase):
    def test_tipo_padrao_determina_o_deslocamento_num_paragrafo(self):
        html = _html()
        for texto in ["Ordem de Serviço 002/2026 - ASCOM", "Ref.: Diligências", "Eu, Fulano de Tal, Delegado de Polícia da Polícia Civil",
                      "O deslocamento dos motoristas Leonardo e Aroldo para o município de <strong>Guarapuava/PR</strong>, <strong>nos dias 25 a 26 de setembro de 2026</strong>",
                      "Cobertura &lt;b&gt;do&lt;/b&gt; evento", "Curitiba, 18 de setembro de 2026", "doc-os--padrao",
                      "Assessoria de Comunicação Social - Rua X, 1 - Curitiba/PR (41) 3000-0000 – ascom@pc.pr.gov.br"]:
            self.assertIn(texto, html)
        self.assertNotIn("Justificativa um.", html)

    def test_demais_tipos_trazem_atribuicoes_justificativas_e_finalidade(self):
        html = _html(dict(TX, tipo_necessidade="CAMINHAO"))
        for texto in ["Ref.: Deslocamento - Caminhão", "O deslocamento da equipe abaixo relacionada:",
                      "<li>Leonardo: condução do caminhão;</li>", "Justificativa um.", "Justificativa dois.",
                      "tem por finalidade garantir a atividade."]:
            self.assertIn(texto, html)
        self.assertEqual(html.count("<li>"), 1)  # item vazio não vira marcador solto

    def test_destino_e_periodo_em_negrito_dentro_da_determinacao_escapada(self):
        tx = dict(TX, tipo_necessidade="CAMINHAO", determinacao="Para <i>Guarapuava/PR</i>, nos dias 25 a 26 de setembro de 2026, apoio.")
        html = _html(tx)
        self.assertIn("Para &lt;i&gt;<strong>Guarapuava/PR</strong>&lt;/i&gt;, <strong>nos dias 25 a 26 de setembro de 2026</strong>, apoio.", html)
        self.assertNotIn("doc-os--padrao", html)

    def test_rodape_pula_o_que_falta(self):
        html = _html(dict(TX, endereco="", telefone=""))
        self.assertIn(">Assessoria de Comunicação Social - ascom@pc.pr.gov.br<", html)

    def test_css_proprio_entra_no_cache(self):
        self.assertIn("ordem_servico.css", [p.name for p in caminhos_dos_templates(OS)])


class FacadeDaOrdemTests(TestCase):
    @override_settings(DOCUMENTOS_PERSIST_ARTEFATOS=False)
    def test_pdf_da_ordem_nasce_do_html(self):
        from documentos.services.facade import DocumentoFacade

        payload = {"institucional": {}, "ordem_servico": {}}
        with mock.patch("documentos.services.pdf_renderer.render_pdf", return_value=b"%PDF-1.7 fake"):
            doc = DocumentoFacade().gerar(tipo=OS, formato=DocumentoFormato.PDF, payload=payload, docxtpl_context=TX, reference="t")
        self.assertEqual(doc.pdf_engine_used, "html_weasyprint")


@skipUnless(weasyprint_disponivel(), "WeasyPrint sem runtime nativo nesta máquina")
class PdfRealDaOrdemTests(SimpleTestCase):
    def test_os_dois_modelos_cabem_em_uma_pagina(self):
        from pypdf import PdfReader

        for tipo in ("PADRAO", "CAMINHAO"):
            with self.subTest(tipo=tipo):
                leitor = PdfReader(io.BytesIO(render_pdf(_html(dict(TX, tipo_necessidade=tipo)), tipo=OS)))
                self.assertEqual(len(leitor.pages), 1)
                texto = leitor.pages[0].extract_text()
                for trecho in ("POLÍCIA CIVIL DO PARANÁ", "DETERMINO", "Fulano de Tal"):
                    self.assertIn(trecho, texto)
