"""
PDF mínimo sem WeasyPrint nem LibreOffice (útil em Windows dev sem GTK).

Usa fpdf2 com fontes core (Helvetica); texto em português é transliterado para ASCII.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Any, Mapping

from documentos.services.types import DocumentoTipo
from documentos.services.formatters import format_document_datetime


def _ascii_fold(value: object) -> str:
    s = format_document_datetime(value) if isinstance(value, datetime) else str(value or "")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if ord(c) < 128)


def _as_lines(payload: Mapping[str, object]) -> list[str]:
    lines: list[str] = []
    inst = payload.get("institucional")
    if isinstance(inst, dict):
        lines.append("=== Institucional ===")
        for k in ("nome_orgao", "sigla_orgao", "unidade", "divisao", "email", "telefone_formatado"):
            v = inst.get(k)
            if v:
                lines.append(f"{k}: {_ascii_fold(v)}")
        lines.append("")

    oficio = payload.get("oficio")
    if isinstance(oficio, dict):
        lines.append("=== Oficio ===")
        for k in (
            "numero_formatado",
            "protocolo",
            "assunto",
            "assunto_oficio",
            "motivo",
            "roteiro",
            "data_criacao",
            "viatura",
            "motorista",
        ):
            v = oficio.get(k)
            if v not in (None, "", []):
                if k == "motivo":
                    lines.append(f"{k}:")
                    lines.append(_ascii_fold(v))
                else:
                    lines.append(f"{k}: {_ascii_fold(v)}")
        serv = oficio.get("servidores")
        if isinstance(serv, list) and serv:
            lines.append("servidores: " + ", ".join(_ascii_fold(x) for x in serv))
        lines.append("")

    just = payload.get("justificativa")
    if isinstance(just, dict) and (just.get("texto") or just.get("exigida")):
        lines.append("=== Justificativa ===")
        lines.append(f"exigida: {just.get('exigida')}")
        if just.get("texto"):
            lines.append(_ascii_fold(just["texto"]))
        lines.append("")

    termo = payload.get("termo")
    if isinstance(termo, dict):
        lines.append("=== Termo de Autorizacao ===")
        p = termo.get("participante")
        if isinstance(p, dict):
            lines.append(f"Servidor: {_ascii_fold(p.get('nome'))}")
            lines.append(f"CPF: {_ascii_fold(p.get('cpf_formatado') or p.get('cpf', ''))}")
        viagem = termo.get("viagem")
        if isinstance(viagem, dict):
            lines.append(f"Destino: {_ascii_fold(viagem.get('destinos_texto'))}")
            lines.append(f"Periodo: {_ascii_fold(viagem.get('periodo'))}")
        transporte = termo.get("transporte")
        if isinstance(transporte, dict):
            lines.append(
                "Transporte: "
                f"{_ascii_fold(transporte.get('placa'))} / {_ascii_fold(transporte.get('motorista'))}"
            )
        textos = termo.get("textos")
        if isinstance(textos, dict):
            for key in ("corpo_autorizacao", "declaracao"):
                if textos.get(key):
                    lines.append(_ascii_fold(textos[key]))

    return lines or ["(sem dados no payload)"]


def render_simple_pdf_bytes(*, tipo: DocumentoTipo, payload: Mapping[str, object]) -> bytes:
    try:
        from fpdf import FPDF
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Instale o pacote 'fpdf2' (pip install fpdf2) para o PDF simplificado de desenvolvimento."
        ) from exc

    pdf = FPDF()
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    usable_w = getattr(pdf, "epw", pdf.w - pdf.l_margin - pdf.r_margin)

    if tipo == DocumentoTipo.TERMO_AUTORIZACAO:
        title = "TERMO DE AUTORIZACAO"
    else:
        title = f"Documento: {tipo.value} (fallback dev — sem layout institucional)"
    pdf.set_font_size(14)
    pdf.multi_cell(usable_w, 8, _ascii_fold(title))
    pdf.ln(4)
    pdf.set_font_size(10)

    for line in _as_lines(payload):
        text = _ascii_fold(line).replace("\r\n", "\n").replace("\r", "\n")
        for chunk in text.split("\n"):
            pdf.multi_cell(usable_w, 5, chunk or " ")

    out: Any = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    if isinstance(out, str):
        return out.encode("latin-1", errors="replace")
    return bytes(out)
