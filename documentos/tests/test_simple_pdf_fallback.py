from django.test import SimpleTestCase
from unittest import skipUnless
from documentos.services.pdf_engine import _fpdf_ok

from documentos.services.adapters.simple_pdf_fallback import render_simple_pdf_bytes
from documentos.services.types import DocumentoTipo


@skipUnless(_fpdf_ok(), "fpdf2 não disponível")
class SimplePdfFallbackTests(SimpleTestCase):
    def test_emits_valid_pdf_magic(self):
        raw = render_simple_pdf_bytes(
            tipo=DocumentoTipo.OFICIO,
            payload={
                "institucional": {"nome_orgao": "Órgão"},
                "oficio": {"numero_formatado": "1/2026", "motivo": "Viagem à Brasília"},
                "justificativa": {"exigida": False, "texto": ""},
            },
        )
        self.assertTrue(raw.startswith(b"%PDF"))
