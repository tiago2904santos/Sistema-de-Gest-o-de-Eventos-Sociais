import os
import sys
import tempfile
from pathlib import Path
from unittest import mock
from unittest import skipUnless

from django.test import SimpleTestCase
from django.test import override_settings

from documentos.services import libreoffice_resolve as lo_mod
from documentos.services.libreoffice_resolve import resolve_libreoffice_binary


class LibreOfficeResolveTests(SimpleTestCase):
    @skipUnless(sys.platform == "win32", "Mockar os.name='nt' quebra pathlib/tempfile fora do Windows")
    @mock.patch.object(lo_mod.os, "name", "nt")
    def test_windows_prefere_soffice_com_quando_exe_tem_irmao_console(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "soffice.exe"
            console = Path(tmp) / "soffice.com"
            exe.touch()
            console.touch()

            with override_settings(DOCUMENTOS_LIBREOFFICE_BINARY=str(exe)):
                self.assertEqual(resolve_libreoffice_binary(), str(console))

    @override_settings(DOCUMENTOS_LIBREOFFICE_BINARY="")
    def test_explicit_setting_empty_uses_discovery(self):
        _ = resolve_libreoffice_binary()
        self.assertTrue(_ is None or Path(_).is_file())

    def test_explicit_path_wins(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
            path = tmp.name
        try:
            with override_settings(DOCUMENTOS_LIBREOFFICE_BINARY=path):
                self.assertEqual(resolve_libreoffice_binary(), path)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_env_documentos_libreoffice_binary_priority_over_settings(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as env_exe:
            env_path = env_exe.name
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as set_exe:
            set_path = set_exe.name
        try:
            with mock.patch.dict(os.environ, {"DOCUMENTOS_LIBREOFFICE_BINARY": env_path}, clear=False):
                with override_settings(DOCUMENTOS_LIBREOFFICE_BINARY=set_path):
                    self.assertEqual(resolve_libreoffice_binary(), env_path)
        finally:
            Path(env_path).unlink(missing_ok=True)
            Path(set_path).unlink(missing_ok=True)

    def test_verify_version_false_accepts_file_without_subprocess(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
            path = tmp.name
        try:
            with override_settings(DOCUMENTOS_LIBREOFFICE_BINARY=path):
                self.assertEqual(resolve_libreoffice_binary(verify_version=False), path)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_verify_version_uses_subprocess(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
            path = tmp.name
        try:
            with override_settings(DOCUMENTOS_LIBREOFFICE_BINARY=path):
                with mock.patch.object(lo_mod, "verify_libreoffice_binary", return_value=False):
                    self.assertIsNone(resolve_libreoffice_binary(verify_version=True))
        finally:
            Path(path).unlink(missing_ok=True)

    @skipUnless(sys.platform == "win32", "Mockar os.name='nt' quebra tempfile fora do Windows")
    @mock.patch.object(lo_mod.os, "name", "nt")
    @mock.patch.object(lo_mod.subprocess, "run", return_value=mock.Mock(returncode=0))
    def test_verify_version_windows_nao_abre_janela(self, m_run):
        with tempfile.NamedTemporaryFile(suffix=".com") as tmp:
            self.assertTrue(lo_mod.verify_libreoffice_binary(tmp.name))

        self.assertEqual(
            m_run.call_args.kwargs["creationflags"],
            getattr(lo_mod.subprocess, "CREATE_NO_WINDOW", 0),
        )

    @skipUnless(sys.platform == "win32", "Mockar os.name='nt' quebra tempfile fora do Windows")
    @mock.patch.object(lo_mod.os, "name", "nt")
    @mock.patch.object(lo_mod.subprocess, "run")
    def test_verify_version_recusa_exe_grafico_sem_irmao_console(self, m_run):
        with tempfile.NamedTemporaryFile(suffix=".exe") as tmp:
            self.assertFalse(lo_mod.verify_libreoffice_binary(tmp.name))

        m_run.assert_not_called()

    def test_shutil_which_used_when_no_explicit(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
            which_path = tmp.name
        try:
            with override_settings(DOCUMENTOS_LIBREOFFICE_BINARY=""):
                with mock.patch.dict(os.environ, {}, clear=False):
                    for key in ("DOCUMENTOS_LIBREOFFICE_BINARY", "SOFFICE_PATH", "LIBREOFFICE_SOFFICE"):
                        os.environ.pop(key, None)
                side_effect = {"soffice": which_path, "libreoffice": None, "lowriter": None}

                def _which(name):
                    return side_effect.get(name)

                with mock.patch.object(lo_mod.shutil, "which", side_effect=_which):
                    out = resolve_libreoffice_binary()
            self.assertEqual(out, which_path)
        finally:
            Path(which_path).unlink(missing_ok=True)
