"""O número, a data e o valor da ordem bancária, lidos do PDF.

No padrão da leitura da nota fiscal (`nota_fiscal.py`): basta anexar o PDF da
OB na etapa 3 e o sistema tira dele o que conseguir. O que não for lido fica
em branco (PDF escaneado, sem texto) e a data, se faltar, é a do dia.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from .nota_fiscal import _DINHEIRO, _texto_do_pdf

# "2026OB012345" (o formato do SIAF/SIAFI) ou "Ordem Bancária nº 12345".
_NUMERO = (
    re.compile(r"(?<![\dA-Z])(\d{4}\s*OB\s*\d{3,})(?!\d)", re.IGNORECASE),
    re.compile(
        r"(?:ORDEM\s+BANC[ÁA]RIA|N[ÚU]MERO\s+DA\s+OB|\bOB\b)\s*(?:N[º°o.]*|n[úu]mero)?\s*[:\-]?\s*(\d[\d./-]{2,})",
        re.IGNORECASE,
    ),
)
_DATA_ROTULADA = re.compile(
    r"(?:DATA\s+(?:DE\s+|DA\s+)?(?:EMISS[ÃA]O|PAGAMENTO|OB|ORDEM\s+BANC[ÁA]RIA)|EMITIDA\s+EM)[^\d]{0,40}?(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_DATA = re.compile(r"(?<!\d)(\d{2}/\d{2}/\d{4})(?!\d)")
_VALOR = re.compile(
    r"VALOR(?:\s+(?:L[ÍI]QUIDO|TOTAL|DA\s+OB|DA\s+ORDEM\s+BANC[ÁA]RIA|PAGO|BRUTO))?[^\d]{0,40}?" + _DINHEIRO,
    re.IGNORECASE,
)


def _data(texto):
    try:
        dia, mes, ano = (int(p) for p in texto.split("/"))
        return date(ano, mes, dia)
    except ValueError:
        return None


def dados_no_texto(texto: str) -> dict:
    """``numero``, ``data`` (date) e ``valor`` (Decimal) da OB; cada um pode faltar."""
    texto = texto or ""
    saida = {"numero": "", "data": None, "valor": None}
    for padrao in _NUMERO:
        achado = padrao.search(texto)
        if achado:
            saida["numero"] = re.sub(r"\s+", "", achado.group(1)).upper().strip(".-/")
            break
    achado = _DATA_ROTULADA.search(texto) or _DATA.search(texto)
    if achado:
        saida["data"] = _data(achado.group(1))
    achado = _VALOR.search(texto)
    if achado:
        saida["valor"] = Decimal(achado.group(1).replace(".", "").replace(",", "."))
    return saida


def dados_da_ob(dados: bytes, paginas: int = 3) -> dict:
    """`dados_no_texto` do PDF (bytes); tudo vazio se não der para ler."""
    return dados_no_texto(_texto_do_pdf(dados, paginas))
