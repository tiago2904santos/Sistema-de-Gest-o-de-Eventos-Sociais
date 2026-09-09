from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from documentos.services.document_cache import build_document_cache_key
from documentos.services.document_cache import build_template_cache_signature
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo


class DocumentCacheKeyTests(SimpleTestCase):
    def test_assinatura_enxerga_o_modelo_html_do_pdf(self):
        """O HTML precisa entrar na impressão digital do modelo.

        O nome registrado é relativo ao motor de templates; concatenado com o
        `BASE_DIR`, apontava para um caminho inexistente e a assinatura ficava
        constante. Consequência: editar o modelo do PDF não invalidava o
        artefato já em cache, e o documento antigo continuava sendo servido.
        """
        assinatura = build_template_cache_signature(
            tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.PDF
        )
        html = Path(settings.BASE_DIR) / "templates" / "documentos" / "pdf" / "oficio.html"
        self.assertTrue(html.exists(), "modelo HTML do ofício ausente")
        self.assertIn(str(html.resolve()), assinatura)
        self.assertNotIn(":missing", assinatura)

    def test_chave_altera_quando_payload_muda(self):
        tpl = build_template_cache_signature(tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.PDF)
        k1 = build_document_cache_key(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.PDF,
            reference="01-2026",
            payload={"a": 1},
            docxtpl_context={"x": "y"},
            attempt_chain=("libreoffice",),
            template_signature=tpl,
        )
        k2 = build_document_cache_key(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.PDF,
            reference="01-2026",
            payload={"a": 2},
            docxtpl_context={"x": "y"},
            attempt_chain=("libreoffice",),
            template_signature=tpl,
        )
        self.assertNotEqual(k1, k2)

    def test_docx_e_pdf_tem_chaves_distintas(self):
        tpl_pdf = build_template_cache_signature(tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.PDF)
        tpl_docx = build_template_cache_signature(tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.DOCX)
        p = {"institucional": {"nome_orgao": "X"}, "oficio": {"numero_formatado": "1"}}
        k_pdf = build_document_cache_key(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.PDF,
            reference="r",
            payload=p,
            docxtpl_context={},
            attempt_chain=("weasyprint",),
            template_signature=tpl_pdf,
        )
        k_docx = build_document_cache_key(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.DOCX,
            reference="r",
            payload=p,
            docxtpl_context={"u": "v"},
            attempt_chain=(),
            template_signature=tpl_docx,
        )
        self.assertNotEqual(k_pdf, k_docx)
