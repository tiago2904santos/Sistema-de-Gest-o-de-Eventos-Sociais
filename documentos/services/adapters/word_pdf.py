"""
Conversão DOCX → PDF via Microsoft Word (Windows / COM apenas).

Não invocar fora de Windows; use `is_word_pdf_available()` antes.
"""

from __future__ import annotations

import importlib.util
import logging
import platform
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_WORD_ERR = (
    "Microsoft Word não está disponível para conversão PDF. "
    "Instale o LibreOffice ou configure outro motor PDF."
)


def word_progid_registrado() -> bool:
    """Word instalado, lendo o registro — sem abrir o programa.

    ``Word.Application\\CLSID`` só existe quando o Office registrou o servidor
    COM: é a mesma informação que o ``DispatchEx`` confirmava, obtida por uma
    leitura de registro em vez de um processo novo.
    """
    try:
        import winreg
    except ImportError:  # fora do Windows
        return False
    try:
        winreg.CloseKey(
            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID")
        )
    except OSError:
        logger.debug("ProgID Word.Application não registrado", exc_info=True)
        return False
    return True


def is_word_pdf_available() -> bool:
    """Sonda barata: NÃO abre o Word.

    A versão anterior fazia ``DispatchEx("Word.Application")`` só para
    responder "sim": 4,5 s no primeiro uso e ~0,8 s nos seguintes, pagos no
    caminho crítico da geração (a cadeia de motores entra na chave de cache do
    documento). Como ``DocumentoFacade`` tenta os motores em ordem e cai para o
    seguinte quando um falha, uma sonda otimista custa no pior caso uma
    tentativa perdida — não um Word aberto a cada janela de sondagem.
    """
    if platform.system() != "Windows":
        return False
    try:
        pywin32_presente = importlib.util.find_spec("win32com") is not None
    except (ImportError, ValueError):
        logger.debug("find_spec de win32com falhou", exc_info=True)
        return False
    if not pywin32_presente:
        return False
    return word_progid_registrado()


def convert_docx_to_pdf_word_com(docx_bytes: bytes) -> bytes:
    if platform.system() != "Windows":
        raise OSError("Conversão via Word COM só é suportada no Windows.")

    try:
        import docx2pdf
    except ImportError:
        docx2pdf = None

    if docx2pdf is not None:
        return _convert_via_docx2pdf(docx_bytes)

    return _convert_via_win32com(docx_bytes)


def _convert_via_docx2pdf(docx_bytes: bytes) -> bytes:
    import docx2pdf

    with tempfile.TemporaryDirectory(prefix="cv3_word_") as tmp:
        in_path = Path(tmp) / "entrada.docx"
        out_path = Path(tmp) / "entrada.pdf"
        in_path.write_bytes(docx_bytes)
        try:
            docx2pdf.convert(str(in_path), str(out_path))
        except Exception as exc:
            logger.warning("docx2pdf.convert falhou: %s", exc, exc_info=True)
            raise RuntimeError(_WORD_ERR) from exc
        if not out_path.is_file():
            raise RuntimeError(_WORD_ERR)
        return out_path.read_bytes()


def _convert_via_win32com(docx_bytes: bytes) -> bytes:
    import pythoncom
    import win32com.client

    wd_format_pdf = 17
    with tempfile.TemporaryDirectory(prefix="cv3_word_") as tmp:
        in_path = Path(tmp) / "entrada.docx"
        out_path = Path(tmp) / "entrada.pdf"
        in_path.write_bytes(docx_bytes)
        pythoncom.CoInitialize()
        word = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(str(in_path), ReadOnly=True)
            try:
                doc.SaveAs(str(out_path), FileFormat=wd_format_pdf)
            finally:
                doc.Close(SaveChanges=0)
        except Exception as exc:
            logger.warning("win32com Word SaveAs PDF falhou: %s", exc, exc_info=True)
            raise RuntimeError(_WORD_ERR) from exc
        finally:
            if word is not None:
                try:
                    word.Quit(SaveChanges=0)
                except Exception:
                    logger.debug("Falha ao encerrar Word após conversão", exc_info=True)
            try:
                pythoncom.CoUninitialize()
            except Exception:
                logger.debug("Falha em CoUninitialize do Word", exc_info=True)
        if not out_path.is_file():
            raise RuntimeError(_WORD_ERR)
        return out_path.read_bytes()
