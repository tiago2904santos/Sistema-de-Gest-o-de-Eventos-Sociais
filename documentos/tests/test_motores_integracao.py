"""Conversões reais; cada motor opcional só roda quando está disponível."""

import io
from unittest import skipUnless

from django.test import SimpleTestCase, override_settings

from documentos.services.adapters.word_pdf import is_word_pdf_available
from documentos.services.libreoffice_resolve import resolve_libreoffice_binary
from documentos.services.pdf_engine import _weasy_import_ok, _fpdf_ok
from documentos.services.facade import DocumentoFacade
from documentos.services.types import DocumentoTipo, DocumentoFormato
from documentos.tests.test_integracao import payload_exemplo


@override_settings(DOCUMENTOS_PERSIST_ARTEFATOS=False, DOCUMENTOS_PDF_AUTO_FALLBACK=False)
# A cadeia antiga (DOCX → conversor) continua valendo para os tipos ainda não
# migrados; aqui ela é exercitada com o ofício, então o caminho HTML nativo é
# desligado só neste teste.
@override_settings(DOCUMENTOS_PDF_HTML_NATIVO=())
class MotoresReaisTests(SimpleTestCase):
    def converter(self, engine):
        from pypdf import PdfReader

        # O fallback simples fica desligado fora de desenvolvimento; aqui o
        # alvo é o motor, não a política, então a precondição é explícita.
        with override_settings(
            DOCUMENTOS_DEFAULT_PDF_ENGINE=engine, DOCUMENTOS_SIMPLE_PDF_FALLBACK=True
        ):
            doc = DocumentoFacade().gerar(
                tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.PDF,
                payload=payload_exemplo(), docxtpl_context={"oficio": "Teste F3"},
            )
        self.assertEqual(doc.pdf_engine_used, engine)
        self.assertTrue(doc.conteudo.startswith(b"%PDF"))
        pages = PdfReader(io.BytesIO(doc.conteudo)).pages
        self.assertGreater(len(pages), 0)
        self.assertIn("F3", " ".join(p.extract_text() for p in pages))

    @skipUnless(is_word_pdf_available(), "Microsoft Word/COM não disponível")
    def test_word(self):
        self.converter("word_com")

    @skipUnless(resolve_libreoffice_binary(verify_version=False), "LibreOffice não disponível")
    def test_libreoffice(self):
        self.converter("libreoffice")

    @skipUnless(_weasy_import_ok(), "WeasyPrint sem bibliotecas nativas")
    def test_weasyprint(self):
        self.converter("weasyprint")

    @skipUnless(_fpdf_ok(), "fpdf2 não disponível")
    def test_fallback_simples(self):
        self.converter("simple_fallback")
