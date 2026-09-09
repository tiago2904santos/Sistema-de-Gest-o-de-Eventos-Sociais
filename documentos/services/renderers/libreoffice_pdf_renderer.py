"""
Extensão opcional: PDF derivado de DOCX via LibreOffice.

A conversão propriamente dita é centralizada em `documentos.services.facade.DocumentoFacade`
quando `DOCUMENTOS_DEFAULT_PDF_ENGINE=libreoffice`.
Este módulo existe como âncora para imports explícitos e documentação.
"""

from __future__ import annotations

from documentos.services.adapters.libreoffice_pdf import convert_docx_to_pdf_libreoffice

__all__ = ["convert_docx_to_pdf_libreoffice"]
