from datetime import datetime

from django.test import SimpleTestCase

from documentos.services.filenames import build_document_filename
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo


class FilenameTests(SimpleTestCase):
    def test_build_document_filename_uses_tipo_ref_timestamp_and_format(self):
        result = build_document_filename(
            DocumentoTipo.OFICIO,
            DocumentoFormato.PDF,
            reference="Ref # 123",
            now=datetime(2026, 5, 8, 10, 30, 45),
        )
        self.assertEqual(result, "oficio_ref_123_20260508-103045.pdf")
