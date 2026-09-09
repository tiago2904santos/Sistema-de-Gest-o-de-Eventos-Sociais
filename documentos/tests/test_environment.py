from unittest import mock

from django.test import SimpleTestCase
from django.test import override_settings

from documentos.services import environment as env_mod
from documentos.services.environment import DocumentEnvironmentReport
from documentos.services.environment import build_document_environment_report


class BuildDocumentEnvironmentReportTests(SimpleTestCase):
    @mock.patch.object(env_mod, "_word_com_available", return_value=(False, "não Windows"))
    @mock.patch.object(env_mod, "_weasyprint_functional", return_value=(False, "GTK"))
    @mock.patch.object(env_mod, "resolve_libreoffice_binary", return_value=None)
    @mock.patch.object(env_mod, "_check_docx", return_value=(True, []))
    def test_pdf_indisponivel_sem_motores(self, *_m):
        with override_settings(DOCUMENTOS_SIMPLE_PDF_FALLBACK=False):
            r = build_document_environment_report()
        self.assertIsInstance(r, DocumentEnvironmentReport)
        self.assertTrue(r.docx_available)
        self.assertFalse(r.pdf_available)
        self.assertIsNone(r.preferred_pdf_engine)
        self.assertIn("libreoffice", r.missing_pdf_engines)
        self.assertTrue(len(r.install_hints) >= 1)

    @mock.patch.object(env_mod, "_word_com_available", return_value=(False, ""))
    @mock.patch.object(env_mod, "_weasyprint_functional", return_value=(True, "ok"))
    @mock.patch.object(env_mod, "resolve_libreoffice_binary", return_value="/usr/bin/libreoffice")
    @mock.patch.object(env_mod, "_check_docx", return_value=(True, []))
    @mock.patch.object(env_mod, "_os_name", return_value="linux")
    def test_linux_prefere_libreoffice_antes_de_weasy(self, *_m):
        with override_settings(DOCUMENTOS_SIMPLE_PDF_FALLBACK=False):
            r = build_document_environment_report()
        self.assertEqual(r.preferred_pdf_engine, "libreoffice")
        self.assertTrue(r.pdf_available)

    @mock.patch.object(env_mod, "_check_docx", return_value=(False, ["docxtpl"]))
    @mock.patch.object(env_mod, "_word_com_available", return_value=(False, ""))
    @mock.patch.object(env_mod, "_weasyprint_functional", return_value=(False, ""))
    @mock.patch.object(env_mod, "resolve_libreoffice_binary", return_value=None)
    def test_docx_missing_lista_pacotes(self, *_m):
        with override_settings(DOCUMENTOS_SIMPLE_PDF_FALLBACK=False):
            r = build_document_environment_report()
        self.assertFalse(r.docx_available)
        self.assertEqual(r.docx_missing_packages, ["docxtpl"])
        self.assertTrue(any("pip install" in h for h in r.install_hints))
