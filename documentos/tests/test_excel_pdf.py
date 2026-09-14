"""A disponibilidade do Excel deve ser a mesma nas threads do servidor."""
import sys
from types import ModuleType
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from documentos.services.adapters.excel_pdf import is_excel_pdf_available


class ExcelProbeTests(SimpleTestCase):
    def executar(self, erro=False):
        com=ModuleType('pythoncom')
        com.CoInitialize=Mock(); com.CoUninitialize=Mock()
        win32=ModuleType('win32com'); client=ModuleType('win32com.client')
        win32.client=client
        excel=Mock()
        def dispatch(_):
            com.CoInitialize.assert_called_once_with()
            if erro: raise RuntimeError('Excel indisponível')
            return excel
        client.DispatchEx=Mock(side_effect=dispatch)
        with patch.dict(sys.modules,{'pythoncom':com,'win32com':win32,'win32com.client':client}), patch('documentos.services.adapters.excel_pdf.platform.system',return_value='Windows'):
            result=is_excel_pdf_available()
        com.CoUninitialize.assert_called_once_with()
        return result,excel

    def test_sonda_inicializa_com_e_fecha_excel(self):
        result,excel=self.executar()
        self.assertTrue(result)
        self.assertFalse(excel.Visible)
        excel.Quit.assert_called_once_with()

    def test_sonda_falha_libera_com(self):
        result,excel=self.executar(erro=True)
        self.assertFalse(result)
        excel.Quit.assert_not_called()
