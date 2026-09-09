from django.test import SimpleTestCase

from documentos.services.exceptions import DocumentTemplateNotFound
from documentos.services.exceptions import DocumentValidationError
from documentos.services.exceptions import DocumentRendererUnavailable
from documentos.services.exceptions import UnresolvedPlaceholderError
from documentos.services.exceptions import UnsupportedDocumentFormat
from documentos.services.exceptions import UnsupportedDocumentType
from documentos.services.renderers import DocumentRenderRequest
from documentos.services.renderers import DocxRenderer
from documentos.services.renderers import PdfRenderer
from documentos.services.renderers import render_document
from documentos.services.templates import DocumentTemplateDefinition
from documentos.services.templates import DocumentTemplateRegistry
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo


class RenderersTests(SimpleTestCase):
    def test_render_document_raises_when_renderer_unavailable(self):
        request = DocumentRenderRequest(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.DOCX,
            payload={"numero": "10"},
            template_content="Ofício {{numero}}",
        )
        with self.assertRaises(DocumentRendererUnavailable):
            render_document(request)

    def test_render_document_raises_when_renderer_incompatible(self):
        request = DocumentRenderRequest(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.DOCX,
            payload={"numero": "10"},
        )
        with self.assertRaises(UnsupportedDocumentFormat):
            render_document(request, renderer=PdfRenderer(adapter=lambda req: b"ok"))

    def test_render_document_raises_when_template_missing_for_format(self):
        request = DocumentRenderRequest(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.PDF,
            payload={"numero": "10"},
        )
        registry = DocumentTemplateRegistry()
        registry.register(
            DocumentTemplateDefinition(
                tipo=DocumentoTipo.OFICIO,
                formato=DocumentoFormato.DOCX,
                template_path="oficio.docx",
            ),
        )
        import documentos.services.renderers as renderers_module

        original_registry = renderers_module.default_template_registry
        renderers_module.default_template_registry = registry
        try:
            with self.assertRaises(DocumentTemplateNotFound):
                render_document(request, renderer=PdfRenderer(adapter=lambda req: b"ok"))
        finally:
            renderers_module.default_template_registry = original_registry

    def test_render_document_raises_when_placeholder_required_is_missing(self):
        request = DocumentRenderRequest(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.DOCX,
            payload={},
        )
        registry = DocumentTemplateRegistry()
        registry.register(
            DocumentTemplateDefinition(
                tipo=DocumentoTipo.OFICIO,
                formato=DocumentoFormato.DOCX,
                template_path="documentos/oficio.docx",
                required_placeholders=("numero",),
            ),
        )

        import documentos.services.renderers as renderers_module

        original_registry = renderers_module.default_template_registry
        renderers_module.default_template_registry = registry
        try:
            with self.assertRaises(DocumentValidationError):
                render_document(request, renderer=DocxRenderer(adapter=lambda req: b"ok"))
        finally:
            renderers_module.default_template_registry = original_registry

    def test_render_document_raises_when_unresolved_placeholder(self):
        request = DocumentRenderRequest(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.DOCX,
            payload={"numero": "10"},
        )
        with self.assertRaises(UnresolvedPlaceholderError):
            render_document(
                request,
                renderer=DocxRenderer(adapter=lambda req: b"ok"),
                template_content="Ofício {{numero}} {{pendente}}",
            )

    def test_render_document_raises_for_unsupported_document_type(self):
        request = DocumentRenderRequest(
            tipo="tipo_invalido",  # type: ignore[arg-type]
            formato=DocumentoFormato.DOCX,
            payload={"numero": "10"},
        )
        with self.assertRaises(UnsupportedDocumentType):
            render_document(request, renderer=DocxRenderer(adapter=lambda req: b"ok"))

    def test_render_document_raises_for_unsupported_format_by_type(self):
        request = DocumentRenderRequest(
            tipo=DocumentoTipo.OFICIO,
            formato="txt",  # type: ignore[arg-type]
            payload={"numero": "10"},
        )
        with self.assertRaises(UnsupportedDocumentFormat):
            render_document(request, renderer=DocxRenderer(adapter=lambda req: b"ok"))

    def test_render_document_returns_content_when_renderer_supports_format(self):
        request = DocumentRenderRequest(
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.DOCX,
            payload={"numero": "10"},
        )
        result, filename = render_document(
            request,
            renderer=DocxRenderer(adapter=lambda req: f"Ofício {req.payload['numero']}".encode("utf-8")),
            template_content="Ofício {{numero}}",
            reference="A-1",
        )
        self.assertEqual(result.content, "Ofício 10".encode("utf-8"))
        self.assertIn("oficio_a-1_", filename)
