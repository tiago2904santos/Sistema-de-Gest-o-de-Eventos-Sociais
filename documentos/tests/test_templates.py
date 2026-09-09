from django.test import SimpleTestCase

from documentos.services.exceptions import DocumentTemplateNotFound
from documentos.services.exceptions import DocumentValidationError
from documentos.services.templates import DocumentTemplateDefinition
from documentos.services.templates import DocumentTemplateRegistry
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo


class TemplatesTests(SimpleTestCase):
    def test_register_duplicate_template_raises(self):
        registry = DocumentTemplateRegistry()
        definition = DocumentTemplateDefinition(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.DOCX,
            template_path="documentos/oficio.docx",
        )
        registry.register(definition)
        with self.assertRaises(DocumentValidationError):
            registry.register(definition)

    def test_get_unknown_template_raises(self):
        registry = DocumentTemplateRegistry()
        with self.assertRaises(DocumentTemplateNotFound):
            registry.get(DocumentoTipo.OFICIO, DocumentoFormato.DOCX)

    def test_get_returns_template_definition(self):
        registry = DocumentTemplateRegistry()
        definition = DocumentTemplateDefinition(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.DOCX,
            template_path="documentos/oficio.docx",
        )
        registry.register(definition)
        loaded = registry.get(DocumentoTipo.OFICIO, DocumentoFormato.DOCX)
        self.assertEqual(loaded.template_path, "documentos/oficio.docx")
        self.assertTrue(registry.has(DocumentoTipo.OFICIO, DocumentoFormato.DOCX))
        self.assertEqual(len(registry.all()), 1)
