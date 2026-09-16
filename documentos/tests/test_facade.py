import hashlib
from unittest import mock

from django.test import SimpleTestCase
from django.test import override_settings

from documentos.services.exceptions import DocumentValidationError
from documentos.services.facade import DocumentoFacade
from documentos.services.pdf_engine import PdfEngineResolution
from documentos.services.templates import DocumentTemplateDefinition
from documentos.services.templates import DocumentTemplateRegistry
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo


@override_settings(DOCUMENTOS_PERSIST_ARTEFATOS=False)
class FacadeTests(SimpleTestCase):
    def test_gerar_docx_requires_payload_fields(self):
        facade = DocumentoFacade()
        with self.assertRaises(DocumentValidationError):
            facade.gerar(
                tipo=DocumentoTipo.OFICIO,
                formato=DocumentoFormato.DOCX,
                payload={},
            )

    def test_gerar_docx_returns_hash(self):
        registry = DocumentTemplateRegistry()
        registry.register(
            DocumentTemplateDefinition(
                tipo=DocumentoTipo.OFICIO,
                formato=DocumentoFormato.DOCX,
                template_path="oficio.docx",
                required_placeholders=("institucional", "oficio"),
            ),
        )
        facade = DocumentoFacade(template_registry=registry)
        payload = {
            "institucional": {"nome_orgao": "X"},
            "oficio": {"numero_formatado": "1/2026"},
            "justificativa": {"exigida": False, "texto": ""},
        }
        flat = {"oficio": "1/2026", "protocolo": "P"}
        with mock.patch.object(facade, "_render_docx", return_value=b"fake-docx") as m_docx:
            out = facade.gerar(
                tipo=DocumentoTipo.OFICIO,
                formato=DocumentoFormato.DOCX,
                payload=payload,
                reference="ref",
                docxtpl_context=flat,
            )
        m_docx.assert_called_once()
        self.assertEqual(m_docx.call_args[0][1], flat)
        self.assertEqual(out.hash_sha256, hashlib.sha256(b"fake-docx").hexdigest())
        self.assertTrue(out.nome_arquivo.endswith(".docx"))

    @override_settings(
        DOCUMENTOS_DEFAULT_PDF_ENGINE="auto",
        DOCUMENTOS_SIMPLE_PDF_FALLBACK=False,
        DOCUMENTOS_PDF_AUTO_FALLBACK=False,
        # Cadeia antiga exercitada com o ofício: caminho HTML nativo desligado aqui.
        DOCUMENTOS_PDF_HTML_NATIVO=(),
    )
    def test_oficio_pdf_com_docxtpl_usa_libreoffice_e_mesmo_contexto(self):
        facade = DocumentoFacade()
        payload = {
            "institucional": {"nome_orgao": "Órgão"},
            "oficio": {"numero_formatado": "01/2026"},
        }
        flat = {"oficio": "01/2026", "protocolo": "12.345.678-9", "assunto_linha": "Linha fixa"}
        res = PdfEngineResolution(
            attempt_chain=("libreoffice",),
            reason="test",
            available_engines=("libreoffice",),
            missing_engines=(),
            install_hints=(),
        )
        with mock.patch("documentos.services.facade.resolve_pdf_engine", return_value=res):
            with mock.patch.object(facade, "_pdf_via_libreoffice", return_value=b"fake-pdf") as m_lo:
                with mock.patch.object(facade, "_render_docx", return_value=b"fake-docx"):
                    out = facade.gerar(
                        tipo=DocumentoTipo.OFICIO,
                        formato=DocumentoFormato.PDF,
                        payload=payload,
                        docxtpl_context=flat,
                    )
        m_lo.assert_called_once()
        self.assertIs(m_lo.call_args.kwargs.get("docxtpl_context"), flat)
        self.assertEqual(out.conteudo, b"fake-pdf")
        self.assertEqual(out.hash_sha256, hashlib.sha256(b"fake-pdf").hexdigest())
