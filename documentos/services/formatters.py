"""
Formatadores puros para textos exibidos em documentos (DOCX/PDF).

`format_document_display` aplica capitalização legível em PT-BR (não é `str.title()`
cego): partículas curtas permanecem em minúsculas no meio do título; siglas conhecidas
são restauradas por `preserve_known_acronyms` após a capitalização base.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import ROUND_HALF_UP
from decimal import Decimal, InvalidOperation
from typing import Final

from django.utils import formats, timezone, translation

# Partículas comuns em títulos (minúsculas quando não são o primeiro token).
_TITLE_LOWER_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "o",
        "as",
        "os",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "e",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "ao",
        "aos",
        "à",
        "às",
        "por",
        "para",
        "com",
        "sem",
        "sobre",
        "entre",
        "até",
    }
)

# Siglas e códigos que devem manter forma canónica após o title-case.
KNOWN_ACRONYMS: Final[frozenset[str]] = frozenset(
    {
        "PR",
        "RJ",
        "SP",
        "MG",
        "RS",
        "SC",
        "BA",
        "DF",
        "GO",
        "PE",
        "CE",
        "AM",
        "PA",
        "AC",
        "RO",
        "RR",
        "AP",
        "TO",
        "MA",
        "PI",
        "RN",
        "PB",
        "SE",
        "AL",
        "ES",
        "MT",
        "MS",
        "RG",
        "CPF",
        "CNH",
        "CEP",
        "DPC",
        "SESP",
        "PCPR",
        "CNPJ",
        "PJ",
        "UF",
    }
)

_DEMO_BRACKET_RE = re.compile(r"^\[\s*([Dd][Ee][Mm][Oo])\s*\]\s*")


def _title_case_word(word: str, *, is_first: bool) -> str:
    if not word:
        return word
    core = word
    punct_prefix = ""
    punct_suffix = ""
    while core and not core[0].isalnum():
        punct_prefix += core[0]
        core = core[1:]
    while core and not core[-1].isalnum():
        punct_suffix = core[-1] + punct_suffix
        core = core[:-1]
    if not core:
        return word
    lower = core.lower()
    if not is_first and lower in _TITLE_LOWER_WORDS:
        return f"{punct_prefix}{lower}{punct_suffix}"
    # Preserva hífen interno: "São-José" -> "São-josé" evitado: segmentar por -
    if "-" in core:
        parts = core.split("-")
        titled = "-".join(_title_case_word(p, is_first=(is_first and i == 0)) for i, p in enumerate(parts))
        return f"{punct_prefix}{titled}{punct_suffix}"
    return f"{punct_prefix}{core[0].upper()}{core[1:].lower()}{punct_suffix}"


def preserve_known_acronyms(text: str) -> str:
    """Substitui tokens que coincidem com siglas conhecidas (case-insensitive) pela forma canónica."""
    if not text or not text.strip():
        return str(text or "")

    def fix_token(tok: str) -> str:
        w = tok
        leading = ""
        trailing = ""
        while w and not w[0].isalnum():
            leading += w[0]
            w = w[1:]
        while w and not w[-1].isalnum():
            trailing = w[-1] + trailing
            w = w[:-1]
        if w and w.isascii() and w.upper() in KNOWN_ACRONYMS:
            return f"{leading}{w.upper()}{trailing}"
        return tok

    return " ".join(fix_token(t) for t in text.split())


def format_document_display(value: object) -> str:
    """
    Capitalização legível para nomes e descrições em documentos.

    Preserva prefixo entre parênteses rectos no estilo [Demo] … (normaliza para [Demo]).
    """
    s = str(value or "").strip()
    if not s:
        return ""

    demo_match = _DEMO_BRACKET_RE.match(s)
    rest = s
    prefix = ""
    if demo_match:
        prefix = "[Demo] "
        rest = s[demo_match.end() :].lstrip()

    words = rest.split()
    if not words:
        return prefix.rstrip()

    parts = [_title_case_word(w, is_first=(i == 0)) for i, w in enumerate(words)]
    body = " ".join(parts)
    body = preserve_known_acronyms(body)
    return (prefix + body).strip()


def format_institucional_rodape_linha(inst: dict) -> str:
    """
    Linha de rodapé institucional (justificativa/termo): nome em title case,
    endereço com vírgulas, telefone e e-mail (e-mail em minúsculas).
    """
    nome_src = str(inst.get("divisao") or "").strip() or str(inst.get("unidade") or "").strip() or str(inst.get("nome_orgao") or "").strip()
    titulo = format_document_display(nome_src) if nome_src else ""

    log = str(inst.get("logradouro") or "").strip()
    log_fmt = format_document_display(log) if log else ""
    num = str(inst.get("numero") or "").strip()
    bai = str(inst.get("bairro") or "").strip()
    bai_fmt = format_document_display(bai) if bai else ""
    linha1 = ", ".join([p for p in (log_fmt, num, bai_fmt) if p])

    cidade = str(inst.get("cidade_endereco") or "").strip()
    uf = str(inst.get("uf") or "").strip().upper()
    cidade_uf = ""
    if cidade and uf:
        cidade_uf = format_city_uf(f"{cidade}/{uf}")
    elif cidade:
        cidade_uf = format_document_display(cidade)
    elif uf:
        cidade_uf = uf

    cep = str(inst.get("cep_formatado") or inst.get("cep") or "").strip()
    cep_part = f"CEP {cep}" if cep else ""

    endereco = ", ".join(x for x in (linha1, cidade_uf, cep_part) if x)

    mid_parts = [p for p in (titulo, endereco) if p]
    mid = " - ".join(mid_parts)

    tel = str(inst.get("telefone_formatado") or inst.get("telefone") or "").strip()
    em = str(inst.get("email") or "").strip().lower()
    tail = " – ".join([p for p in (tel, em) if p])

    if mid and tail:
        return f"{mid}, {tail}"
    return mid or tail


def format_city_uf(value: object) -> str:
    """
    Normaliza "LONDRINA/PR" ou "LONDRINA / PR" para "Londrina/PR" (espaço único junto à barra).
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "/" not in raw:
        return format_document_display(raw)
    left, right = raw.split("/", 1)
    city = left.strip()
    uf = right.strip()
    city_fmt = format_document_display(city) if city else ""
    if len(uf) == 2 and uf.isalpha():
        uf_fmt = uf.upper()
    else:
        uf_fmt = format_document_display(uf) if uf else ""
    if city_fmt and uf_fmt:
        return f"{city_fmt}/{uf_fmt}"
    return city_fmt or uf_fmt


def format_currency_br(value: object) -> str:
    """
    Formato monetário BR: R$1.500,00 (milhar com ponto, decimais com vírgula).

    Converte o valor para `Decimal` (nunca formata `float` directamente).
    """
    if value is None or value == "":
        return ""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    neg = q < 0
    if neg:
        q = -q
    with translation.override("pt-br"):
        body = "R$" + formats.number_format(q, decimal_pos=2, force_grouping=True)
    return f"-{body}" if neg else body


def format_document_datetime(value: datetime, pattern: str = "%d/%m/%Y %H:%M") -> str:
    """Horário do documento no fuso ativo do Django (São Paulo por padrão)."""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime(pattern)


def format_valor_extenso_display(value: object) -> str:
    """
    Valor por extenso para leitura em documento: evita o texto todo em maiúsculas
    vindas do legado ou de rotinas numéricas; fica em frase normal com só a
    primeira letra maiúscula (ex.: «Cento e cinquenta reais»).
    """
    s = str(value or "").strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    lower = s.lower()
    return lower[0].upper() + lower[1:] if lower else ""
