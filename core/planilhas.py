"""Normalização de células vindas das planilhas de controle da ASCOM.

Os relatórios mensais (publicações, atendimento à imprensa) são preenchidos
à mão: horários no formato "17h03", "16h" ou "9:15", marcações "SIM"/"NÃO"/"-"
e datas ora como data real, ora como texto. Estas funções deixam tudo no
formato dos modelos; são usadas pelos comandos de importação e pelos forms.
"""

import datetime as dt
import hashlib
import re
import unicodedata

VAZIOS = {"", "-", "--", "—", "?", "n/a", "na"}

FORMATOS_HORA = ["%H:%M", "%Hh%M", "%Hh", "%H:%M:%S", "%HH%M", "%H.%M"]


def limpa(texto):
    """Colapsa espaços internos e apara as pontas; None vira ""."""
    if texto is None:
        return ""
    return re.sub(r"[ \t\r\f\v]+", " ", str(texto)).strip()


def limpa_multilinha(texto):
    """Preserva quebras de linha (campos de fonte/andamento), sem excesso."""
    if texto is None:
        return ""
    linhas = [limpa(linha) for linha in str(texto).replace("\r", "").split("\n")]
    corpo = "\n".join(linhas).strip()
    return re.sub(r"\n{3,}", "\n\n", corpo)


def norm(texto):
    """Minúsculas sem acentos — chave de comparação de nomes."""
    base = limpa(texto).lower()
    return "".join(
        c
        for c in unicodedata.normalize("NFD", base)
        if unicodedata.category(c) != "Mn"
    )


def vazio(valor):
    return valor is None or limpa(valor).lower() in VAZIOS


def como_data(valor):
    """date a partir de datetime/date ou de texto dd/mm/aaaa; senão None."""
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", limpa(valor))
    if not m:
        return None
    ano = int(m.group(3))
    if ano < 100:
        ano += 2000
    try:
        return dt.date(ano, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_hora(valor):
    """time a partir de "17h03", "16h", "9:15", "17:03:00" ou time/datetime.

    Devolve None para vazio ou para texto que não é um horário único (uma
    célula com vários horários, por exemplo, fica como texto).
    """
    if isinstance(valor, dt.datetime):
        return valor.time().replace(second=0, microsecond=0)
    if isinstance(valor, dt.time):
        return valor.replace(second=0, microsecond=0)
    if vazio(valor):
        return None
    texto = limpa(valor).lower().replace(" ", "")
    m = re.fullmatch(r"(\d{1,2})(?:[h:\.](\d{1,2})?)?(?::\d{1,2})?", texto)
    if not m:
        return None
    hora = int(m.group(1))
    minuto = int(m.group(2) or 0)
    if hora > 23 or minuto > 59:
        return None
    return dt.time(hora, minuto)


def sim_nao(valor):
    """True/False para SIM/NÃO (e variações); None para vazio ou outro texto."""
    texto = norm(valor)
    if texto in {"sim", "s", "yes", "x", "ok"}:
        return True
    if texto in {"nao", "n", "no"}:
        return False
    return None


def chave_importacao(*partes):
    """Hash estável das partes que identificam a linha na planilha."""
    base = "|".join(limpa(parte).lower() for parte in partes)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def linha_vazia(linha):
    return not any(not vazio(celula) for celula in linha)
