from datetime import datetime

from django.test import RequestFactory
from django.test import SimpleTestCase

from documentos.services.exceptions import UnsupportedDocumentFormat
from documentos.services.responses import build_download_response
from documentos.services.responses import build_inline_pdf_response
from documentos.services.responses import build_inline_pdf_response_from_download_response
from documentos.services.responses import get_content_type_for_format
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo


class ResponsesTests(SimpleTestCase):
    def test_build_download_response_sets_headers(self):
        response = build_download_response(
            content=b"conteudo",
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.DOCX,
            reference="AB-99",
            now=datetime(2026, 5, 8, 10, 40, 0),
        )
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertIn("oficio_ab-99_20260508-104000.docx", response["Content-Disposition"])

    def test_build_download_response_sets_pdf_content_type(self):
        response = build_download_response(
            content=b"pdf",
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.PDF,
            reference="AB-99",
            now=datetime(2026, 5, 8, 10, 40, 0),
        )
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(".pdf", response["Content-Disposition"])

    def test_get_content_type_for_format_raises_when_unsupported(self):
        with self.assertRaises(UnsupportedDocumentFormat):
            get_content_type_for_format("txt")  # type: ignore[arg-type]

    def test_build_inline_pdf_response_uses_inline_disposition(self):
        factory = RequestFactory()
        request = factory.get("/doc.pdf")
        now = datetime(2026, 5, 8, 10, 40, 0)
        resp = build_inline_pdf_response(
            request,
            content=b"%PDF-1.4\n%x",
            tipo=DocumentoTipo.OFICIO,
            reference="AB-99",
            now=now,
            cache_hit=False,
            x_document_sha256="deadbeef",
        )
        self.assertIn("inline", resp["Content-Disposition"])
        self.assertNotIn("attachment", resp["Content-Disposition"])
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertEqual(resp["X-Document-Cache"], "MISS")
        self.assertEqual(resp["X-Document-SHA256"], "deadbeef")
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")
        _ = b"".join(resp.streaming_content)

    def test_build_inline_from_download_preserves_cache_and_sha(self):
        factory = RequestFactory()
        request = factory.get("/")
        dl = build_download_response(
            content=b"%PDF-1.4\n",
            tipo=DocumentoTipo.JUSTIFICATIVA,
            formato=DocumentoFormato.PDF,
            reference="J-1",
            now=datetime(2026, 5, 8, 10, 40, 0),
            cache_hit=True,
        )
        dl["X-Document-SHA256"] = "abc123"
        inline = build_inline_pdf_response_from_download_response(
            request,
            dl,
            tipo=DocumentoTipo.JUSTIFICATIVA,
            reference="J-1",
            now=datetime(2026, 5, 8, 10, 40, 0),
        )
        self.assertIn("inline", inline["Content-Disposition"])
        self.assertEqual(inline["X-Document-Cache"], "HIT")
        self.assertEqual(inline["X-Document-SHA256"], "abc123")
        _ = b"".join(inline.streaming_content)
