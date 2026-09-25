"""Achados em texto corrido: CPF, valor, data e nº de protocolo.

Tudo aqui recebe o texto que saiu de um PDF (ou do OCR, ou de um e-mail) e
devolve o que reconheceu, na ordem em que aparece, sem repetir. Nada é
gravado e nada é registrado em log: o texto traz nomes e CPFs.

O texto extraído de PDF é bagunçado — valor antes do rótulo, palavras
coladas, hífen tipográfico no lugar do comum. Por isso as funções procuram
o formato do dado, e não a frase em volta; quem precisa de contexto
("VALOR DO SAQUE R$ …") usa `normalizar` e faz a própria busca.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal
from decimal import InvalidOperation

from core.utils.masks import validar_cpf_digitos

__all__ = [
    "MESES",
    "normalizar",
    "achar_cpfs",
    "achar_cpfs_mascarados",
    "achar_valores",
    "achar_datas",
    "achar_protocolos",
    "achar_cnpjs",
    "data_de",
    "valor_de",
]

# Hífens e travessões que os geradores de PDF usam no lugar do "-".
_TRACOS = str.maketrans({c: "-" for c in "‐‑‒–—―−"})

#: Meses por extenso e abreviados, já sem acento, para `achar_datas`.
MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}


def normalizar(s: str) -> str:
    """Caixa alta, sem acento e com os espaços colapsados.

    Usa a decomposição de compatibilidade (NFKD), e não só a canônica: ela
    também desfaz ligaduras ("ﬁ" de "Certiﬁcado", comum em PDF de portal),
    o "º" (vira "O") e o espaço inseparável. Travessões viram "-".
    """
    decomposto = unicodedata.normalize("NFKD", str(s or ""))
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_acento.translate(_TRACOS).upper().split())


def _unicos(itens):
    vistos = set()
    saida = []
    for item in itens:
        if item not in vistos:
            vistos.add(item)
            saida.append(item)
    return saida


# ─────────────────────────────────────────────────────────────────
# CPF
# ─────────────────────────────────────────────────────────────────

_CPF_FORMATADO = re.compile(r"(?<![\d./-])(\d{3})\.(\d{3})\.(\d{3})\s?-\s?(\d{2})(?![\d/])")
_CPF_CRU = re.compile(r"(?<![\d./-])(\d{11})(?![\d/])")
# Máscaras: o eProtocolo usa X, os bancos * ou •. O \x7f é o "•" de PDF que o
# grava na posição 127 da WinAnsi (o extrator devolve o código cru).
_M = r"[*Xx•●∙·\x7f]"
_CPF_MEIO = re.compile(rf"(?<![\d*Xx•●\x7f]){_M}{{3}}\.?\s?(\d{{3}})\.?\s?(\d{{3}})\s?-?\s?{_M}{{2}}(?![\d*•●\x7f])")
_CPF_PONTAS = re.compile(rf"(?<![\d.])(\d{{3}})\.?\s?{_M}{{3}}\.?\s?{_M}{{3}}\s?-?\s?(\d{{2}})(?!\d)")


def achar_cpfs(texto: str) -> list[str]:
    """CPFs completos (11 dígitos, sem máscara), na ordem em que aparecem.

    Formatado ("123.456.789-09") vale como CPF mesmo com dígito verificador
    errado — é erro de digitação no documento, não outro número. Onze
    dígitos soltos só valem se o dígito verificador conferir: sem isso,
    telefone com DDD e pedaço de chave de NF-e passariam por CPF.
    """
    texto = str(texto or "").translate(_TRACOS)
    achados = []
    for m in _CPF_FORMATADO.finditer(texto):
        achados.append((m.start(), "".join(m.groups())))
    for m in _CPF_CRU.finditer(texto):
        if validar_cpf_digitos(m.group(1)):
            achados.append((m.start(), m.group(1)))
    return _unicos(cpf for _, cpf in sorted(achados))


# Como o OCR costuma devolver a máscara: "**.512.222-**", "000,512.222-.0",
# "123.**."*-02" (asterisco some ou vira aspas; bolinha vira 0/o; ponto vira vírgula).
_MO = r"[*Xx•●∙·\x7f\"'°oO0]"
_CPF_MEIO_OCR = re.compile(
    rf"(?<![\dA-Za-z])({_MO}{{1,3}})[.,]?\s?(\d{{3}})[.,]\s?(\d{{3}})\s?-\s?({_MO.replace(']', '.,]')}{{1,2}})(?!\d)"
)
_CPF_PONTAS_OCR = re.compile(rf"(?<![\d.])(\d{{3}})[.,]\s?{_MO}{{1,3}}[.,\"']?\s?{_MO}{{1,3}}\s?-\s?(\d{{2}})(?!\d)")


def achar_cpfs_mascarados(texto: str, *, tolerante: bool = False) -> list[tuple[str, str]]:
    """CPFs mascarados, como `("meio", "456789")` ou `("pontas", "12300")`.

    - "meio": `***.456.789-**` (bancos, gov.br, rodapé do eProtocolo com X);
      devolve os 6 dígitos visíveis, que são `cpf[3:9]`.
    - "pontas": `123.***.***-00` (como o próprio sistema mascara); devolve
      os 3 primeiros e os 2 últimos, que são `cpf[:3] + cpf[9:]`.

    Com `tolerante`, aceita também a máscara como o OCR a devolve
    ("**.456.789-**", "000,456.789-.0"); serve para texto lido de imagem,
    quando a busca normal não achou nada.
    """
    texto = str(texto or "").translate(_TRACOS)
    achados = []
    for m in _CPF_MEIO.finditer(texto):
        achados.append((m.start(), ("meio", m.group(1) + m.group(2))))
    for m in _CPF_PONTAS.finditer(texto):
        achados.append((m.start(), ("pontas", m.group(1) + m.group(2))))
    if tolerante:
        for m in _CPF_MEIO_OCR.finditer(texto):
            # Máscara toda de dígitos (000…-00) é CPF de verdade, não máscara.
            if (m.group(1) + m.group(4)).isdigit():
                continue
            achados.append((m.start(), ("meio", m.group(2) + m.group(3))))
        for m in _CPF_PONTAS_OCR.finditer(texto):
            achados.append((m.start(), ("pontas", m.group(1) + m.group(2))))
    return _unicos(item for _, item in sorted(achados))


_CNPJ = re.compile(r"(?<![\d./-])(\d{2})\.?(\d{3})\.?(\d{3})/(\d{4})-?(\d{2})(?![\d/])")


def achar_cnpjs(texto: str) -> list[str]:
    """CNPJs (14 dígitos, sem máscara), na ordem em que aparecem."""
    texto = str(texto or "").translate(_TRACOS)
    return _unicos("".join(m.groups()) for m in _CNPJ.finditer(texto))


# ─────────────────────────────────────────────────────────────────
# Valor
# ─────────────────────────────────────────────────────────────────

_VALOR = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d+),(\d{2})(?![\d,])")


def valor_de(texto: str) -> Decimal | None:
    """O valor de um trecho como "1.600,00" ou "R$ 80,00"; None se não for valor."""
    m = _VALOR.search(str(texto or ""))
    if not m:
        return None
    try:
        return Decimal(f"{m.group(1).replace('.', '')}.{m.group(2)}")
    except InvalidOperation:  # pragma: no cover - a regex só deixa passar dígitos
        return None


def achar_valores(texto: str) -> list[Decimal]:
    """Valores no formato brasileiro ("1.600,00", "R$ 80,00"), na ordem.

    Exige a vírgula com dois centavos: número de quantidade ("80"), de
    documento ("2026.050731.000") ou com quatro casas ("20,0000", preço
    unitário de contrato) fica de fora.
    """
    saida = []
    for m in _VALOR.finditer(str(texto or "")):
        try:
            saida.append(Decimal(f"{m.group(1).replace('.', '')}.{m.group(2)}"))
        except InvalidOperation:  # pragma: no cover
            continue
    return _unicos(saida)


# ─────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────

_DATA_NUM = re.compile(r"(?<![\d/.-])(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})(?![\d/-]|\.\d)")
_DATA_ISO = re.compile(r"(?<![\d/.-])(\d{4})[/.-](\d{2})[/.-](\d{2})(?![\d/-]|\.\d)")
_NOMES_MES = "|".join(
    sorted((nome.replace("MARCO", "MAR[ÇC]O") for nome in MESES), key=len, reverse=True)
)
_DATA_EXTENSO = re.compile(
    rf"(?<!\d)(\d{{1,2}})(?:º|°|o)?\s*(?:de\s+|[/.-]\s*)?({_NOMES_MES})\.?\s*(?:de\s+|[/.-]\s*)?(\d{{4}})(?!\d)",
    re.IGNORECASE,
)


def _data(dia, mes, ano) -> date | None:
    try:
        ano = int(ano)
        if ano < 100:
            ano += 2000
        return date(ano, int(mes), int(dia))
    except (TypeError, ValueError):
        return None


def data_de(texto: str) -> date | None:
    """A primeira data de um trecho ("21/09/2026", "21 de setembro de 2026"); None se não houver."""
    datas = achar_datas(texto)
    return datas[0] if datas else None


def achar_datas(texto: str) -> list[date]:
    """Datas válidas, na ordem em que aparecem.

    Aceita "21/09/2026", "21/09/26", "21.09.2026", "21-09-2026",
    "2025.10.21" (assinatura digital), "21 de setembro de 2026",
    "21 SET 2026" e "21/set/2026". Data impossível (31/02) é ignorada.
    """
    bruto = str(texto or "").translate(_TRACOS)
    achados = []
    for m in _DATA_NUM.finditer(bruto):
        d = _data(*m.groups())
        if d:
            achados.append((m.start(), d))
    for m in _DATA_ISO.finditer(bruto):
        d = _data(m.group(3), m.group(2), m.group(1))
        if d:
            achados.append((m.start(), d))
    for m in _DATA_EXTENSO.finditer(bruto):
        d = _data(m.group(1), MESES[normalizar(m.group(2))], m.group(3))
        if d:
            achados.append((m.start(), d))
    return _unicos(d for _, d in sorted(achados, key=lambda item: item[0]))


# ─────────────────────────────────────────────────────────────────
# Protocolo do eProtocolo
# ─────────────────────────────────────────────────────────────────

_PROTOCOLO = re.compile(r"(?<![\d.,/-])(\d{2})\.?(\d{3})\.?(\d{3})\s?-\s?(\d)(?![\d.,/-])")
_ANTES_RG = re.compile(r"\bRG\b[^\d]{0,12}$", re.IGNORECASE)


def achar_protocolos(texto: str) -> list[str]:
    """Números de protocolo do eProtocolo (9 dígitos, sem máscara), na ordem.

    O formato é "26.613.666-8" (os pontos podem faltar; o hífen do dígito
    não). O RG de 9 dígitos tem a mesma máscara, então número precedido de
    "RG" (até "RG n.º: ") fica de fora.
    """
    texto = str(texto or "").translate(_TRACOS)
    saida = []
    for m in _PROTOCOLO.finditer(texto):
        if _ANTES_RG.search(texto[max(0, m.start() - 16):m.start()]):
            continue
        saida.append("".join(m.groups()))
    return _unicos(saida)
