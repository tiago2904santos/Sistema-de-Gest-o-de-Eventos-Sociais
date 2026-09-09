from unittest import mock

from django.test import SimpleTestCase
from django.test import override_settings

from documentos.services.facade import DocumentoFacade
from documentos.services.facade import build_default_facade
from documentos.services.pdf_engine import PdfEngineResolution
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo


@override_settings(DOCUMENTOS_LIBREOFFICE_BINARY="/fake/soffice")
class FacadePdfSingleDocxTests(SimpleTestCase):
    @mock.patch("documentos.services.facade.resolve_libreoffice_binary", return_value="/fake/soffice")
    @mock.patch("documentos.services.facade.convert_docx_to_pdf_libreoffice", return_value=b"%PDF-1 fake")
    @mock.patch("documentos.services.facade.resolve_pdf_engine")
    def test_libreoffice_chama_render_docx_uma_vez(self, m_resolve, *_m):
        m_resolve.return_value = PdfEngineResolution(
            attempt_chain=("libreoffice",),
            reason="test",
        )
        calls: list[int] = []

        def track_render(self, template_def, payload, *, template_path_override=None):
            calls.append(1)
            return b"PK\x03\x04fake-docx"

        with mock.patch.object(DocumentoFacade, "_render_docx", track_render):
            facade = build_default_facade()
            out, eng = facade._render_pdf(
                DocumentoTipo.OFICIO,
                facade._templates.get(DocumentoTipo.OFICIO, DocumentoFormato.PDF),
                {"institucional": {}, "oficio": {}},
                docxtpl_context={"a": "b"},
            )
        self.assertEqual(eng, "libreoffice")
        self.assertTrue(out.startswith(b"%PDF"))
        self.assertEqual(len(calls), 1)
