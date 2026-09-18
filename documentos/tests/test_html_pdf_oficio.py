"""Caminho HTML → PDF do ofício: contexto único, folha institucional, marcação
de editáveis e o encaixe na façade (chave de cache própria, contingência).

Os testes que precisam do WeasyPrint de verdade ficam atrás de
`skipUnless(weasyprint_disponivel())`, como os demais testes de motor: sem o
runtime GTK eles não rodam, e o resto continua valendo.
"""

import io
from unittest import mock, skipUnless

from django.test import SimpleTestCase, TestCase, override_settings

from documentos.services.document_context import contexto_de_payload, imagens_para
from documentos.services.pdf_renderer import (
    caminhos_dos_templates,
    render_pdf,
    renderizar_html,
    tipo_e_html_nativo,
    weasyprint_disponivel,
)
from documentos.services.types import DocumentoFormato, DocumentoTipo

PAYLOAD = {
    "institucional": {"cidade_endereco": "Curitiba"},
    "oficio": {"numero_formatado": "023/2026", "motivo": "Participação em reunião institucional"},
    "justificativa": {"exigida": False},
}
TX = {
    "oficio": "023/2026", "assunto_oficio": "(Autorização)", "assunto_linha": "Solicitação de autorização e concessão de diárias.",
    "assunto_termo": "autorização", "data_do_oficio": "10/09/2026", "unidade": "ASCOM", "orgao_destino": "Gabinete do Delegado Geral Adjunto",
    "protocolo": "12.345.678-9", "col_servidor": "Maria da Silva\nJoão Souza", "col_rgcpf": "RG 1\nRG 2", "col_cargo": "APJ\nAPJ",
    "col_solicitacao": "10\n11", "destinos_bloco": "Brasília/DF", "diarias_x": "2 x 100%", "diaria": "R$ 500,00 (quinhentos reais)",
    "col_ida_saida": "Saída Curitiba/PR: 10/09/2026 08:00", "col_ida_chegada": "Chegada Brasília/DF: 10/09/2026 12:00",
    "col_volta_saida": "Saída Brasília/DF: 12/09/2026 15:00", "col_volta_chegada": "Chegada Curitiba/PR: 12/09/2026 19:00",
    "viatura": "Viatura oficial", "placa": "ABC-1D23", "motorista_formatado": "João Souza", "combustivel": "Gasolina", "tipo_viatura": "Caracterizada",
    "armamento": "Sim", "custo": "( X ) UNIDADE - DPC\n(   ) OUTRA INSTITUIÇÃO", "motivo": "Participação em reunião institucional",
    "nome_chefia": "Fulano de Tal", "cargo_chefia": "Delegado", "unidade_cabecalho": "ASSESSORIA DE COMUNICAÇÃO",
    "nome_destinatario": "Beltrano", "cargo_destinatario": "Delegado Geral Adjunto", "unidade_rodape": "ASCOM",
    "equipe": [
        {"nome": "Maria da Silva", "cpf": "123.456.789-00", "cargo": "APJ", "solicitacao": "10"},
        {"nome": "João Souza", "cpf": "987.654.321-00", "cargo": "APJ", "solicitacao": "11"},
    ],
    "endereco": "Rua X, 1 - Centro", "telefone": "(41) 3000-0000", "email": "ascom@pc.pr.gov.br",
}


class ContextoETemplateTests(SimpleTestCase):
    def test_oficio_e_html_nativo(self):
        self.assertTrue(tipo_e_html_nativo(DocumentoTipo.OFICIO))
        self.assertTrue(tipo_e_html_nativo(DocumentoTipo.TERMO_AUTORIZACAO))
        self.assertTrue(tipo_e_html_nativo(DocumentoTipo.JUSTIFICATIVA))
        self.assertTrue(tipo_e_html_nativo(DocumentoTipo.ORDEM_SERVICO))
        self.assertTrue(tipo_e_html_nativo(DocumentoTipo.PLANO_TRABALHO))
        self.assertTrue(tipo_e_html_nativo(DocumentoTipo.RELATORIO_TECNICO))
        self.assertTrue(tipo_e_html_nativo(DocumentoTipo.DIARIO_BORDO))

    def test_imagens_por_modo(self):
        self.assertTrue(imagens_para("pdf")["brasao"].startswith("file://"))
        self.assertIn("/static/img/brasao-pcpr.png", imagens_para("editor")["brasao"])

    def test_html_do_pdf_reproduz_o_documento_sem_marcacao_de_edicao(self):
        html = renderizar_html(DocumentoTipo.OFICIO, contexto_de_payload(DocumentoTipo.OFICIO, PAYLOAD, TX, modo="pdf"), modo="pdf")
        for texto in ["SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA", "POLÍCIA CIVIL DO PARANÁ", "ASSESSORIA DE COMUNICAÇÃO",
                      "Ofício Nº <strong>023/2026</strong> (Autorização)", "solicito autorização e medidas",
                      "<td>Maria da Silva</td>", "<td>987.654.321-00</td>",
                      "Brasília/DF", "R$ 500,00 (quinhentos reais)", ">Roteiro de retorno<", "Participação em reunião institucional",
                      "cartão corporativo vigente", "Fulano de Tal", "DR. Beltrano", "Curitiba – Pr.", "ascom@pc.pr.gov.br",
                      "brasao-pcpr.png", "marca-pcpr.png"]:
            self.assertIn(texto, html)
        self.assertNotIn("data-doc-campo", html)
        self.assertNotIn("data-doc-bloco", html)
        self.assertNotIn("RG", html)  # o ofício não traz mais o RG da equipe
        self.assertIn("<th>CPF</th>", html)

    def test_modo_editor_marca_so_os_campos_do_registro(self):
        ctx = contexto_de_payload(DocumentoTipo.OFICIO, PAYLOAD, TX, modo="editor", campos_editaveis={"motivo": {}})
        html = renderizar_html(DocumentoTipo.OFICIO, ctx, modo="editor")
        self.assertIn('data-doc-campo="motivo"', html)
        self.assertNotIn('data-doc-campo="protocolo"', html)
        self.assertIn('data-doc-bloco="declaracao_cartao"', html)
        self.assertIn("<style>", html)  # CSS comum inline, para a folha da tela

    def test_bloco_documental_usa_override_e_escapa_html(self):
        blocos = {"declaracao_cartao": {"conteudo": "Texto <b>do</b> usuário\nsegunda linha", "editado": True}}
        html = renderizar_html(DocumentoTipo.OFICIO, contexto_de_payload(DocumentoTipo.OFICIO, PAYLOAD, TX, modo="editor", blocos=blocos, edicao=True), modo="editor")
        self.assertIn("Texto &lt;b&gt;do&lt;/b&gt; usuário<br>segunda linha", html)
        self.assertIn('data-doc-override="1"', html)
        self.assertNotIn("cartão corporativo vigente", html)

    def test_conteudo_de_campo_e_escapado(self):
        tx = dict(TX, motivo="<script>alert(1)</script>")
        html = renderizar_html(DocumentoTipo.OFICIO, contexto_de_payload(DocumentoTipo.OFICIO, PAYLOAD, tx, modo="pdf"), modo="pdf")
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert", html)

    def test_assinatura_de_cache_enxerga_folha_base_e_css(self):
        nomes = [p.name for p in caminhos_dos_templates(DocumentoTipo.OFICIO)]
        self.assertEqual(nomes, ["oficio.html", "base_institucional.html", "documento.css", "documento-impressao.css", "oficio.css"])


@skipUnless(weasyprint_disponivel(), "WeasyPrint sem runtime nativo nesta máquina")
class PdfRealTests(SimpleTestCase):
    def _texto(self, pdf):
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(pdf))
        return leitor, "\n".join(p.extract_text() for p in leitor.pages)

    def test_pdf_valido_com_cabecalho_rodape_acentos_e_tabela(self):
        pdf = render_pdf(renderizar_html(DocumentoTipo.OFICIO, contexto_de_payload(DocumentoTipo.OFICIO, PAYLOAD, TX, modo="pdf"), modo="pdf"), tipo=DocumentoTipo.OFICIO)
        self.assertTrue(pdf.startswith(b"%PDF"))
        leitor, texto = self._texto(pdf)
        self.assertEqual(len(leitor.pages), 1)
        # O título sai em caixa alta pela folha do documento; a conferência é
        # do conteúdo, não da caixa em que ele foi desenhado.
        for trecho in ["POLÍCIA CIVIL DO PARANÁ", "OFÍCIO Nº 023/2026", "PARTICIPAÇÃO EM REUNIÃO INSTITUCIONAL", "BRASÍLIA/DF", "BELTRANO"]:
            self.assertIn(trecho, texto.upper())

    def test_documento_longo_pagina_e_repete_cabecalho(self):
        tx = dict(TX, motivo="Linha de motivo. " * 700)
        pdf = render_pdf(renderizar_html(DocumentoTipo.OFICIO, contexto_de_payload(DocumentoTipo.OFICIO, PAYLOAD, tx, modo="pdf"), modo="pdf"))
        leitor, _ = self._texto(pdf)
        self.assertGreater(len(leitor.pages), 1)
        for pagina in leitor.pages:
            self.assertIn("POLÍCIA CIVIL DO PARANÁ", pagina.extract_text())


class FacadeCaminhoHtmlTests(TestCase):
    """O encaixe na façade: chave própria e contingência só em desenvolvimento."""

    def _facade(self):
        from documentos.services.facade import DocumentoFacade

        return DocumentoFacade()

    @override_settings(DOCUMENTOS_PERSIST_ARTEFATOS=False)
    def test_pdf_do_oficio_nasce_do_html_quando_o_motor_existe(self):
        with mock.patch("documentos.services.pdf_renderer.render_pdf", return_value=b"%PDF-1.7 fake") as m:
            doc = self._facade().gerar(tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.PDF, payload=PAYLOAD, docxtpl_context=TX, reference="t")
        self.assertEqual(doc.conteudo, b"%PDF-1.7 fake")
        self.assertEqual(doc.pdf_engine_used, "html_weasyprint")
        self.assertEqual(m.call_count, 1)

    @override_settings(DOCUMENTOS_PERSIST_ARTEFATOS=False, DEBUG=False, DOCUMENTOS_PDF_HTML_FALLBACK_DOCX=False)
    def test_sem_motor_em_producao_e_erro_e_nao_cai_no_docx(self):
        from documentos.services.exceptions import DocumentRendererUnavailable, DocumentValidationError

        with mock.patch("documentos.services.pdf_renderer.render_pdf", side_effect=DocumentRendererUnavailable("sem GTK")):
            with mock.patch("documentos.services.facade.resolve_pdf_engine") as cadeia:
                with self.assertRaises(DocumentValidationError):
                    self._facade().gerar(tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.PDF, payload=PAYLOAD, docxtpl_context=TX, reference="t")
        cadeia.assert_not_called()

    def test_chave_de_cache_do_html_difere_da_cadeia_antiga(self):
        from documentos.services.document_cache import build_document_cache_key, build_template_cache_signature

        assinatura = build_template_cache_signature(tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.PDF)
        self.assertIn("base_institucional.html", assinatura)
        nova = build_document_cache_key(tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.PDF, reference="r", payload=PAYLOAD, docxtpl_context=TX, attempt_chain=("html_weasyprint",), template_signature=assinatura)
        antiga = build_document_cache_key(tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.PDF, reference="r", payload=PAYLOAD, docxtpl_context=TX, attempt_chain=("word_com",), template_signature=assinatura)
        self.assertNotEqual(nova, antiga)
