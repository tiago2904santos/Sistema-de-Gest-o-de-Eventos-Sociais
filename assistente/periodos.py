"""Converter o jeito que as pessoas falam de tempo em datas de verdade.

"em setembro", "dia 18", "essa semana", "amanhã" — tudo isso vira um par de
datas antes de chegar a qualquer filtro. É determinístico de propósito: data
errada em documento de viagem é diária paga errada, e um modelo de linguagem
não deve ser a última palavra sobre isso.

A regra do ano implícito, que é a que mais confunde: um mês sem ano ("setembro")
significa o próximo setembro que ainda não terminou. Em março de 2026,
"setembro" é 2026; em novembro de 2026, "setembro" é 2027. Falar de um mês que
já passou exige dizer o ano, e é assim que se evita gerar viagem no passado por
descuido.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re

from core.normalizers import normalize_spaces, remove_accents

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
    "dezembro": 12,
}


def _chave(texto: str) -> str:
    return remove_accents(normalize_spaces(texto or "")).lower()


def fim_do_mes(ano: int, mes: int) -> dt.date:
    return dt.date(ano, mes, calendar.monthrange(ano, mes)[1])


def periodo_do_mes(mes: int, ano: int | None = None, *, hoje: dt.date | None = None):
    """Primeiro e último dia do mês, resolvendo o ano implícito."""
    hoje = hoje or dt.date.today()
    if ano is None:
        ano = hoje.year if mes >= hoje.month else hoje.year + 1
    return dt.date(ano, mes, 1), fim_do_mes(ano, mes)


def interpretar(texto: str, *, hoje: dt.date | None = None):
    """Devolve ``(inicio, fim)`` ou ``(None, None)`` se não houver tempo no texto.

    Reconhece, nesta ordem de prioridade: intervalo explícito ("de 18/09 a
    20/09"), data completa, mês nomeado (com ou sem ano), atalhos relativos e
    "dia N" solto.
    """
    hoje = hoje or dt.date.today()
    alvo = _chave(texto)
    if not alvo:
        return None, None

    intervalo = re.search(
        r"\b(?:de\s+)?(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\s*(?:a|ate|-)\s*"
        r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?",
        alvo,
    )
    if intervalo:
        d1, m1, a1, d2, m2, a2 = intervalo.groups()
        inicio = _montar(int(d1), int(m1), a1, hoje)
        fim = _montar(int(d2), int(m2), a2 or a1, hoje)
        if inicio and fim:
            return inicio, fim

    completa = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", alvo)
    if completa:
        dia, mes, ano = completa.groups()
        data = _montar(int(dia), int(mes), ano, hoje)
        if data:
            return data, data

    for nome, numero in MESES.items():
        if not re.search(rf"\b{nome}\b", alvo):
            continue
        ano = re.search(rf"\b{nome}\b(?:\s+de)?\s+(\d{{4}})", alvo)
        return periodo_do_mes(numero, int(ano.group(1)) if ano else None, hoje=hoje)

    if re.search(r"\bhoje\b", alvo):
        return hoje, hoje
    if re.search(r"\bamanha\b", alvo):
        return hoje + dt.timedelta(days=1), hoje + dt.timedelta(days=1)
    if re.search(r"\b(essa|esta|desta|dessa)\s+semana\b", alvo):
        inicio = hoje - dt.timedelta(days=hoje.weekday())
        return inicio, inicio + dt.timedelta(days=6)
    if re.search(r"\b(proxima|que vem)\b.*\bsemana\b|\bsemana\s+(que vem|proxima)\b", alvo):
        inicio = hoje - dt.timedelta(days=hoje.weekday()) + dt.timedelta(days=7)
        return inicio, inicio + dt.timedelta(days=6)
    if re.search(r"\b(esse|este|deste|desse)\s+mes\b", alvo):
        return periodo_do_mes(hoje.month, hoje.year, hoje=hoje)

    dia_solto = re.search(r"\bdia\s+(\d{1,2})\b", alvo)
    if dia_solto:
        data = _proximo_dia(int(dia_solto.group(1)), hoje)
        if data:
            return data, data
    return None, None


def _montar(dia: int, mes: int, ano, hoje: dt.date):
    if not 1 <= mes <= 12:
        return None
    if ano is None:
        ano_int = hoje.year if (mes, dia) >= (hoje.month, hoje.day) else hoje.year + 1
    else:
        ano_int = int(ano)
        if ano_int < 100:
            ano_int += 2000
    try:
        return dt.date(ano_int, mes, dia)
    except ValueError:
        return None


def _proximo_dia(dia: int, hoje: dt.date):
    """"dia 18" sem mês: o próximo dia 18 a partir de hoje, inclusive."""
    mes, ano = hoje.month, hoje.year
    if dia < hoje.day:
        mes, ano = (1, ano + 1) if mes == 12 else (mes + 1, ano)
    try:
        return dt.date(ano, mes, dia)
    except ValueError:
        return None
