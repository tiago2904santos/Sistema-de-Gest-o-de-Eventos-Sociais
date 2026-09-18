"""Caminho HTML → PDF do Plano de Trabalho: os dois .docx de origem (um evento e
vários eventos) em um template só, na folha ASCOM, com as oito seções numeradas."""

import io
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase, override_settings

from documentos.services.document_context import contexto_de_payload
from documentos.services.pdf_renderer import caminhos_dos_templates, render_pdf, renderizar_html, weasyprint_disponivel
from documentos.services.types import DocumentoFormato, DocumentoTipo

PLANO = DocumentoTipo.PLANO_TRABALHO
TX = {
    "numero_plano_trabalho": "05/2026/ASCOM", "unidade": "ASSESSORIA DE COMUNICAÇÃO SOCIAL",
    "unidade_rodape": "Assessoria de Comunicação Social", "endereco": "Rua X, 1 - Curitiba/PR", "telefone": "", "email": "ascom@pc.pr.gov.br",
    "contextualizacao": "Primeiro parágrafo <b>do</b> contexto.\n\nSegundo parágrafo.",
    "metas": "• Meta um\n• Meta dois", "atividades": "• Atividade um", "recursos_necessarios": "• Recurso um",
    "data_evento": "dias 5 a 6 de outubro de 2026", "destinos": "Guarapuava/PR", "horario_de_atendimento": "09:00 até 17:00",
    "efetivos": "2 Motoristas\n1 Agente", "unidade_movel": "", "valor_do_plano": "Valor total: R$755,44 (setecentos...).",
    "valor_blocos": [], "coordenacao": "Fica designado o coordenador.", "consideracao_final": "Considerações.",
    "sede": "Curitiba", "data_extenso": "18 de setembro de 2026", "nome_chefia": "Fulano de Tal", "cargo_chefia": "Delegado",
    "is_multi_evento": False, "eventos": [],
}
EVENTO = {
    "data_header": "Dias 05 a 06 de outubro de 2026", "titulo": "Dias 05 a 06 de outubro de 2026 - PCPR NA COMUNIDADE",
    "local": "Guarapuava/PR", "horario": "09:00 até 17:00", "efetivo": "2 Motoristas", "unidade_movel": "",
    "metas": "• Meta do evento", "atividades": "• Atividade do evento", "recursos": "• Recurso do evento",
}
EVENTO_2 = dict(EVENTO, data_header="Dia 07 de outubro de 2026", titulo="Dia 07 de outubro de 2026 - PCPR NA COMUNIDADE",
                local="Pitanga/PR", metas="• Meta do segundo", atividades="• Atividade do segundo", recursos="• Recurso do segundo")
VALOR_EVENTO = {"rotulo": "Valor do evento dias:", "texto": " 05 a 06/10/2026: R$377,72 (trezentos...)."}
VALOR_TOTAL = {"rotulo": "Valor total:", "texto": " R$755,44 (setecentos...).\nValor correspondente a 1 x 100%."}
TX_MULTI = dict(
    TX, is_multi_evento=True, eventos=[EVENTO, EVENTO_2], metas="", atividades="", recursos_necessarios="", valor_do_plano=object(),
    horario_de_atendimento="", efetivos="", valor_blocos=[VALOR_EVENTO, VALOR_TOTAL],
)


def _html(tx=TX, modo="pdf"):
    return renderizar_html(PLANO, contexto_de_payload(PLANO, {}, tx, modo=modo), modo=modo)


class TemplateDoPlanoTests(SimpleTestCase):
    def test_plano_de_um_evento(self):
        html = _html()
        for texto in ["Plano de Trabalho Nº 05/2026/ASCOM", "<p class=\"doc-plano__texto\">Primeiro parágrafo &lt;b&gt;do&lt;/b&gt; contexto.</p>",
                      "<p class=\"doc-plano__texto\">Segundo parágrafo.</p>", "• Meta um<br>• Meta dois",
                      "<strong>Datas:</strong> dias 5 a 6 de outubro de 2026;", "<strong>Efetivo total:</strong> 2 Motoristas<br>1 Agente;",
                      "Fica designado o coordenador.", "Curitiba, 18 de setembro de 2026", "Fulano de Tal",
                      "Assessoria de Comunicação Social - Rua X, 1 - Curitiba/PR ascom@pc.pr.gov.br"]:
            self.assertIn(texto, html)
        self.assertEqual(html.count('class="doc-plano__secao"'), 8)
        for resto in ("{#", "#}", "{%", "%}", "{{", "}}"):
            self.assertNotIn(resto, html)  # nada de sintaxe de template vazando para o documento

    def test_ordem_das_secoes_e_quebras_de_pagina(self):
        html = _html()
        ordem = ["Breve contextualização", "Atuação", "Atividades a serem desenvolvidas", "Metas estabelecidas",
                 "Recursos necessários", "Valor total do plano", "Coordenador do evento", "Considerações finais"]
        posicoes = [html.index(f">{titulo}</h2>") for titulo in ordem]
        self.assertEqual(posicoes, sorted(posicoes))
        self.assertRegex(html, r'<section class="doc-plano__bloco doc-plano__bloco--nova-pagina">\s*<h2 class="doc-plano__secao">Atuação</h2>')
        fim = html[html.index('<div class="doc-plano__fim">'):]
        for trecho in ("Coordenador do evento", "Considerações finais", "Fulano de Tal"):
            self.assertIn(trecho, fim)
        self.assertNotIn('class="doc-quebra"', html)  # a linha de quebra é só da tela
        self.assertEqual(_html(modo="editor").count('class="doc-quebra"'), 2)

    def test_plano_de_varios_eventos_repete_os_blocos_por_evento(self):
        html = _html(TX_MULTI)
        for texto in ["Dias 05 a 06 de outubro de 2026:", "• Meta do evento", "• Recurso do evento",
                      '<p class="doc-plano__evento">Dias 05 a 06 de outubro de 2026 - PCPR NA COMUNIDADE</p>', "<strong>Local:</strong> Guarapuava/PR;",
                      "<strong>Valor total:</strong> R$755,44 (setecentos...).<br>Valor correspondente a 1 x 100%."]:
            self.assertIn(texto, html)
        self.assertNotIn("<strong>Datas:</strong>", html)  # no de vários eventos a data vai no título de cada evento
        self.assertNotIn("object at", html)  # o RichText do DOCX não vaza para o HTML
        # Cada evento é um grupo inteiro (data + lista), e cada seção um bloco: nenhum se parte entre páginas.
        self.assertEqual(html.count('class="doc-plano__grupo"'), 6)  # 2 eventos x (atividades, metas, recursos)
        self.assertEqual(html.count('class="doc-plano__grupo doc-plano__atuacao"'), 2)
        self.assertIn('<div class="doc-plano__detalhes">', html)

    def test_varios_eventos_com_um_evento_so_sai_como_o_plano_de_um_evento(self):
        html = _html(dict(TX_MULTI, eventos=[EVENTO]))
        self.assertNotIn("Dias 05 a 06 de outubro de 2026:", html)  # sem a data sobre cada lista
        self.assertNotIn("Valor do evento", html)
        for texto in ["<strong>Datas:</strong> dias 5 a 6 de outubro de 2026;", "<strong>Local:</strong> Guarapuava/PR;",
                      "<strong>Horário de atendimento:</strong> 09:00 até 17:00;", "<strong>Efetivo total:</strong> 2 Motoristas;",
                      "• Meta do evento", "• Atividade do evento", "• Recurso do evento", "<strong>Valor total:</strong> R$755,44"]:
            self.assertIn(texto, html)

    def test_valor_do_plano_de_um_evento_com_rotulo_em_negrito(self):
        self.assertIn("<strong>Valor total:</strong> R$755,44 (setecentos...).", _html())

    def test_css_proprio_entra_no_cache(self):
        self.assertIn("plano_trabalho.css", [p.name for p in caminhos_dos_templates(PLANO)])


class FacadeDoPlanoTests(TestCase):
    @override_settings(DOCUMENTOS_PERSIST_ARTEFATOS=False)
    def test_pdf_do_plano_nasce_do_html(self):
        from documentos.services.facade import DocumentoFacade

        payload = {"institucional": {}, "plano": {}}
        with mock.patch("documentos.services.pdf_renderer.render_pdf", return_value=b"%PDF-1.7 fake"):
            doc = DocumentoFacade().gerar(tipo=PLANO, formato=DocumentoFormato.PDF, payload=payload, docxtpl_context=TX, reference="t")
        self.assertEqual(doc.pdf_engine_used, "html_weasyprint")


@skipUnless(weasyprint_disponivel(), "WeasyPrint sem runtime nativo nesta máquina")
class PdfRealDoPlanoTests(SimpleTestCase):
    def test_paginas_numeradas_com_cabecalho_em_todas(self):
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(render_pdf(_html(dict(TX, consideracao_final="Linha longa de considerações. " * 60)), tipo=PLANO)))
        self.assertGreater(len(leitor.pages), 2)
        self.assertNotIn("ATUAÇÃO", leitor.pages[0].extract_text())  # a primeira página é só capa e contexto
        self.assertIn("2. ATUAÇÃO", leitor.pages[1].extract_text())
        ultima = leitor.pages[-1].extract_text()
        for trecho in ("7. COORDENADOR DO EVENTO", "8. CONSIDERAÇÕES FINAIS", "Fulano de Tal"):
            self.assertIn(trecho, ultima)
        for numero, pagina in enumerate(leitor.pages, start=1):
            texto = pagina.extract_text()
            self.assertIn("POLÍCIA CIVIL DO PARANÁ", texto)
            self.assertIn(str(numero), texto.splitlines()[-1])
