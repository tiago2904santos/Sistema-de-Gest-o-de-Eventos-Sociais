from django.test import SimpleTestCase

from documentos.services.exceptions import DocumentValidationError
from documentos.services.exceptions import UnresolvedPlaceholderError
from documentos.services.placeholders import ensure_no_unresolved_placeholders
from documentos.services.placeholders import ensure_required_placeholders
from documentos.services.placeholders import extract_placeholders
from documentos.services.placeholders import render_template_content


class PlaceholderTests(SimpleTestCase):
    def test_extract_placeholders(self):
        placeholders = extract_placeholders("Olá {{nome}}, ofício {{ numero }}")
        self.assertEqual(placeholders, {"nome", "numero"})

    def test_extract_placeholders_removes_duplicates(self):
        placeholders = extract_placeholders("{{nome}} - {{ nome }} - {{nome}}")
        self.assertEqual(placeholders, {"nome"})

    def test_extract_placeholders_supports_underscore(self):
        placeholders = extract_placeholders("{{numero_oficio}}")
        self.assertEqual(placeholders, {"numero_oficio"})

    def test_ensure_required_placeholders_raises_when_missing(self):
        with self.assertRaises(DocumentValidationError):
            ensure_required_placeholders({"nome": "Tiago"}, ("nome", "numero"))

    def test_ensure_no_unresolved_placeholders_raises(self):
        with self.assertRaises(UnresolvedPlaceholderError):
            ensure_no_unresolved_placeholders("Documento {{pendente}}")

    def test_render_template_content_replaces_values(self):
        result = render_template_content("Ofício {{numero}}", {"numero": 22})
        self.assertEqual(result, "Ofício 22")
