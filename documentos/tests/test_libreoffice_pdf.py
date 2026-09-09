from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from documentos.services.adapters import libreoffice_pdf


class LibreOfficePdfTests(SimpleTestCase):
    @mock.patch.object(libreoffice_pdf.subprocess, "run")
    def test_conversao_usa_uri_de_perfil_valida(self, run):
        def fake_run(command, **_kwargs):
            outdir = Path(command[command.index("--outdir") + 1])
            (outdir / "entrada.pdf").write_bytes(b"%PDF-1.4\n")
            return mock.Mock(returncode=0)

        run.side_effect = fake_run

        result = libreoffice_pdf.convert_docx_to_pdf_libreoffice(
            docx_bytes=b"docx",
            libreoffice_binary="soffice",
        )

        command = run.call_args.args[0]
        profile_argument = next(item for item in command if item.startswith("-env:UserInstallation="))
        self.assertTrue(profile_argument.startswith("-env:UserInstallation=file:///"))
        self.assertNotIn("\\", profile_argument)
        self.assertEqual(result, b"%PDF-1.4\n")

