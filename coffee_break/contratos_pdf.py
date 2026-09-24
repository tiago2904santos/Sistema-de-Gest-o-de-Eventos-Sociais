"""Os dados de um contrato ou termo aditivo, lidos do PDF.

Basta anexar o documento: o sistema diz o que ele é (contrato ou termo
aditivo), de quem é (o CNPJ e a razão social do contratado) e tira o
número, o GMS, o lote, a quantidade, os valores e a vigência — no modelo
dos contratos da SESP (Setor/Centro de Contratos e Convênios), como o
0762/2024 da Favo e Mel e o aditivo 0355/2025 que o prorrogou.

A vigência do termo aditivo está escrita ("prorrogada a vigência ... a
partir de 31/10/2025 até 30/10/2026"). O contrato inicial só diz o prazo
("1 (um) ano"): a data sai estimada a partir da inserção no protocolo, e o
aditivo seguinte a corrige.
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

CNPJ_SESP = "76416932000181"

_DATA = r"(\d{2})/(\d{2})/(\d{4})"


def _normal(texto):
    """Sem acentos e com os traços unificados, para as expressões abaixo."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.replace("–", "-").replace("—", "-").replace("º", "o").replace("°", "o")


def _data(d, m, a):
    try:
        return date(int(a), int(m), int(d))
    except ValueError:
        return None


def _decimal(valor):
    try:
        return Decimal(valor.replace(".", "").replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _inteiro(valor):
    digitos = re.sub(r"\D", "", valor or "")
    return int(digitos) if digitos else None


def _mais_anos(inicio, anos):
    try:
        return inicio.replace(year=inicio.year + anos)
    except ValueError:  # 29/02
        return inicio.replace(year=inicio.year + anos, day=28)


def texto_do_pdf(dados: bytes) -> str:
    try:
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(dados))
        return "\n".join((pagina.extract_text() or "") for pagina in leitor.pages)
    except Exception:
        return ""


def ler(texto: str) -> dict:
    """O que o documento é e o que ele diz. Chaves ausentes: não achou."""
    t = _normal(texto)
    plano = re.sub(r"\s+", " ", t)
    dados: dict = {}

    aditivo = re.search(r"TERMO ADITIVO No\s*(\d{1,5}/\d{4})", plano, re.IGNORECASE)
    cabecalho = re.search(
        r"CONTRATO\s*-\s*No\s*(\d{1,5}/\d{4})\s*-\s*GMS\s*No\s*(\d{1,6}/\d{4})", plano, re.IGNORECASE
    )
    referencia = re.search(
        r"Contrato\s*n[o.]*\s*(\d{1,5}/\d{4})\s*-\s*GMS\s*(?:No\s*)?(\d{1,6}/\d{4})", plano, re.IGNORECASE
    )
    if aditivo:
        dados["tipo"] = "aditivo"
        dados["termo_aditivo"] = aditivo.group(1)
        if referencia:
            dados["numero"], dados["numero_gms"] = referencia.groups()
        elif cabecalho:
            dados["numero"], dados["numero_gms"] = cabecalho.groups()
        else:
            ao = re.search(r"CONTRATO\s*No\s*(\d{1,5}/\d{4})\s*-\s*GMS\s*No\s*(\d{1,6}/\d{4})", plano, re.IGNORECASE)
            if ao:
                dados["numero"], dados["numero_gms"] = ao.groups()
    elif cabecalho:
        dados["tipo"] = "contrato"
        dados["numero"], dados["numero_gms"] = cabecalho.groups()

    # O contratado: a razão social e o CNPJ (o outro CNPJ é o da SESP).
    contratado = re.search(
        r"CONTRATAD[OA](?:\s*\(A\))?\s*:\s*(.+?)\s*,?\s*CNPJ\s*n?o?\s*:?\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})",
        plano, re.IGNORECASE,
    )
    if contratado:
        dados["razao_social"] = re.sub(r"\s+", " ", contratado.group(1)).strip(" ,")
        dados["cnpj"] = re.sub(r"\D", "", contratado.group(2))

    lote = re.search(r"LOTE\s*-?\s*0*(\d{1,2})\b", plano)
    if lote:
        dados["numero_lote"] = int(lote.group(1))

    # A linha da tabela do objeto: quantidade, valor unitário e total (no
    # aditivo de reajuste, o terceiro é o valor unitário repactuado). O
    # apostilamento corrige a tabela ("Leia-se"): vale a última.
    linhas = re.findall(r"(\d{1,3}(?:\.\d{3})+|\d{2,7})\s+R\$\s*([\d.]+,\d{2,4})\s+R\$\s*([\d.]+,\d{2,4})", plano)
    if linhas:
        quantidade, unitario, terceiro = linhas[-1]
        dados["quantidade"] = _inteiro(quantidade)
        if re.search(r"REPACTUADO", plano, re.IGNORECASE):
            dados["valor_unitario"] = _decimal(terceiro)
        else:
            dados["valor_unitario"] = _decimal(unitario)
            dados["valor_total"] = _decimal(terceiro)
    total = re.search(r"valor total do contrato e de R\$\s*([\d.]+,\d{2})", plano, re.IGNORECASE)
    if total:
        dados["valor_total"] = _decimal(total.group(1))
    reajuste = re.search(r"passando de R\$\s*[\d.]+,\d{2}.*?para R\$\s*([\d.]+,\d{2})", plano, re.IGNORECASE)
    if reajuste:
        dados["valor_total"] = _decimal(reajuste.group(1))

    # Vigência: a do aditivo está escrita; a do contrato, só o prazo.
    prorrogada = re.search(
        r"prorrogada a vigencia.{0,120}?a partir\s+de\s+" + _DATA + r"\s+(?:ate|a)\s+" + _DATA, plano, re.IGNORECASE
    )
    if prorrogada:
        dados["vigencia_inicio"] = _data(*prorrogada.groups()[:3])
        dados["vigencia_fim"] = _data(*prorrogada.groups()[3:])
        dados["vigencia_estimada"] = False
    else:
        prazo = re.search(r"prazo de vigencia do contrato e de\s*(\d{1,2})\s*\([^)]*\)\s*(ano|anos|mes|meses)", plano, re.IGNORECASE)
        inserido = re.search(r"Inserido ao Protocolo\s*[\d.\-]+\s*por\s*.+?em:?\s*" + _DATA, plano, re.IGNORECASE)
        if prazo and inserido:
            inicio = _data(*inserido.groups())
            quantos = int(prazo.group(1))
            if inicio:
                if prazo.group(2).lower().startswith("ano"):
                    fim = _mais_anos(inicio, quantos) - timedelta(days=1)
                else:
                    fim = inicio + timedelta(days=30 * quantos - 1)
                dados["vigencia_inicio"], dados["vigencia_fim"] = inicio, fim
                dados["vigencia_estimada"] = True
    dados["da_sesp"] = CNPJ_SESP in re.sub(r"\D", "", plano)
    return dados
