import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

import documentos.management.commands.documentos_check as cmd_mod
from documentos.services.environment import DocumentEngineStatus
from documentos.services.environment import DocumentEnvironmentReport


def _report(**kwargs):
    defaults = dict(
        os_name="windows",
        python_version="3.12.0",
        docx_available=True,
        docx_missing_packages=[],
        pdf_available=True,
        preferred_pdf_engine="libreoffice",
        available_pdf_engines=["libreoffice"],
        missing_pdf_engines=["word_com"],
        libreoffice_binary="/x/soffice",
        microsoft_word_available=False,
        weasyprint_available=False,
        simple_fallback_available=False,
        install_hints=[],
        engine_details=[
            DocumentEngineStatus(name="libreoffice", available=True, detail="/x/soffice"),
        ],
    )
    defaults.update(kwargs)
    return DocumentEnvironmentReport(**defaults)


class DocumentosCheckCommandTests(SimpleTestCase):
    def test_sem_nenhum_motor_reporta_indisponibilidade_sem_traceback(self):
        from contextlib import ExitStack
        from documentos.services import environment

        with ExitStack() as stack:
            for name, value in {
                "_check_docx": (False, ["docxtpl", "python-docx"]),
                "_word_com_available": (False, "ausente"),
                "_weasyprint_functional": (False, "ausente"),
                "resolve_libreoffice_binary": None,
                "_fpdf2_available": False,
            }.items():
                stack.enter_context(mock.patch.object(environment, name, return_value=value))
            out = StringIO()
            with self.assertRaises(SystemExit) as result:
                call_command("documentos_check", "--json", stdout=out)
        self.assertEqual(result.exception.code, 2)
        data = json.loads(out.getvalue())
        self.assertFalse(data["pdf_available"])
        self.assertEqual(len(data["missing_pdf_engines"]), 4)

    def test_aviso_da_biblioteca_nao_contamina_json(self):
        def probe():
            print("aviso de biblioteca nativa")
            return _report()

        out, err = StringIO(), StringIO()
        with mock.patch.object(cmd_mod, "build_document_environment_report", side_effect=probe):
            with mock.patch.object(cmd_mod.sys, "exit"):
                call_command("documentos_check", "--json", stdout=out, stderr=err)
        self.assertTrue(json.loads(out.getvalue())["pdf_available"])
        self.assertIn("aviso", err.getvalue())

    @mock.patch.object(cmd_mod, "build_document_environment_report", return_value=_report())
    @mock.patch.object(cmd_mod.sys, "exit")
    def test_exit_zero_quando_ok(self, m_exit, *_m):
        out = StringIO()
        call_command("documentos_check", stdout=out)
        m_exit.assert_called_with(0)

    @mock.patch.object(cmd_mod, "build_document_environment_report", return_value=_report(docx_available=False))
    @mock.patch.object(cmd_mod.sys, "exit")
    def test_exit_dois_sem_docx(self, m_exit, *_m):
        call_command("documentos_check")
        m_exit.assert_called_with(2)

    @mock.patch.object(
        cmd_mod,
        "build_document_environment_report",
        return_value=_report(pdf_available=False, preferred_pdf_engine=None),
    )
    @mock.patch.object(cmd_mod.sys, "exit")
    def test_exit_um_sem_pdf(self, m_exit, *_m):
        call_command("documentos_check")
        m_exit.assert_called_with(1)

    @mock.patch.object(cmd_mod, "build_document_environment_report", return_value=_report())
    @mock.patch.object(cmd_mod.sys, "exit")
    def test_json_stdout(self, m_exit, *_m):
        buf = StringIO()
        call_command("documentos_check", "--json", stdout=buf)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["os_name"], "windows")
        m_exit.assert_called_with(0)
