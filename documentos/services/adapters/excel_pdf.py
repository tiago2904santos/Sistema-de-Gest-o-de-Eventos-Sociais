"""Conversão XLSX → PDF via Microsoft Excel (Windows / COM apenas).

Não invocar fora de Windows; use `is_excel_pdf_available()` antes.
"""

from __future__ import annotations

import logging
import platform
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_EXCEL_ERR = (
    "Microsoft Excel não está disponível para conversão PDF. "
    "Instale o LibreOffice ou configure outro motor PDF."
)


def is_excel_pdf_available() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    excel = None
    try:
        import win32com.client

        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        return True
    except Exception:
        logger.debug("Excel COM indisponível", exc_info=True)
        return False
    finally:
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                logger.debug("Falha ao encerrar Excel após probe", exc_info=True)


def convert_xlsx_to_pdf_excel_com(xlsx_bytes: bytes) -> bytes:
    if platform.system() != "Windows":
        raise OSError("Conversão via Excel COM só é suportada no Windows.")

    import pythoncom
    import win32com.client

    xl_type_pdf = 0  # xlTypePDF
    with tempfile.TemporaryDirectory(prefix="cv3_excel_") as tmp:
        in_path = Path(tmp) / "entrada.xlsx"
        out_path = Path(tmp) / "entrada.pdf"
        in_path.write_bytes(xlsx_bytes)
        pythoncom.CoInitialize()
        excel = None
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            wb = excel.Workbooks.Open(str(in_path), ReadOnly=True)
            try:
                wb.ExportAsFixedFormat(xl_type_pdf, str(out_path))
            finally:
                wb.Close(SaveChanges=0)
        except Exception as exc:
            logger.warning("Excel ExportAsFixedFormat PDF falhou: %s", exc, exc_info=True)
            raise RuntimeError(_EXCEL_ERR) from exc
        finally:
            if excel is not None:
                try:
                    excel.Quit()
                except Exception:
                    logger.debug("Falha ao encerrar Excel após conversão", exc_info=True)
            try:
                pythoncom.CoUninitialize()
            except Exception:
                logger.debug("Falha em CoUninitialize do Excel", exc_info=True)
        if not out_path.is_file():
            raise RuntimeError(_EXCEL_ERR)
        return out_path.read_bytes()
