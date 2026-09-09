from django.test import SimpleTestCase

from documentos.services.exceptions import DocumentValidationError
from documentos.services.exceptions import UnsupportedDocumentType
from documentos.services.registry import DocumentoRegistry
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo
from documentos.services.types import DocumentoTipoDefinicao


class DocumentoRegistryTests(SimpleTestCase):
    def test_register_duplicate_tipo_raises(self):
        registry = DocumentoRegistry()
        definicao = DocumentoTipoDefinicao(
            tipo=DocumentoTipo.OFICIO,
            label="Ofício",
            descricao="Documento de teste",
            formatos_permitidos=(DocumentoFormato.DOCX,),
        )
        registry.register(definicao)

        with self.assertRaises(DocumentValidationError):
            registry.register(definicao)

    def test_get_unknown_tipo_raises(self):
        registry = DocumentoRegistry()
        with self.assertRaises(UnsupportedDocumentType):
            registry.get(DocumentoTipo.OFICIO)

    def test_supports_format_true_for_allowed_format(self):
        definicao = DocumentoTipoDefinicao(
            tipo=DocumentoTipo.OFICIO,
            label="Ofício",
            descricao="Documento de teste",
            formatos_permitidos=(DocumentoFormato.DOCX, DocumentoFormato.PDF),
        )
        self.assertTrue(definicao.supports_format(DocumentoFormato.PDF))

    def test_supports_format_false_for_disallowed_format(self):
        definicao = DocumentoTipoDefinicao(
            tipo=DocumentoTipo.OFICIO,
            label="Ofício",
            descricao="Documento de teste",
            formatos_permitidos=(DocumentoFormato.DOCX,),
        )
        self.assertFalse(definicao.supports_format(DocumentoFormato.PDF))
