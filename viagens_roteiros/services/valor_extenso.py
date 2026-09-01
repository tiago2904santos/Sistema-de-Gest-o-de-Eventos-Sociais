"""Valor monetário por extenso, em português.

Portado da Central de Viagens 3 sem alteração de comportamento: o texto sai
em documento oficial, e mudar a grafia mudaria o documento.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


_UNIDADES = {
    0: "zero",
    1: "um",
    2: "dois",
    3: "três",
    4: "quatro",
    5: "cinco",
    6: "seis",
    7: "sete",
    8: "oito",
    9: "nove",
    10: "dez",
    11: "onze",
    12: "doze",
    13: "treze",
    14: "quatorze",
    15: "quinze",
    16: "dezesseis",
    17: "dezessete",
    18: "dezoito",
    19: "dezenove",
}

_DEZENAS = {
    20: "vinte",
    30: "trinta",
    40: "quarenta",
    50: "cinquenta",
    60: "sessenta",
    70: "setenta",
    80: "oitenta",
    90: "noventa",
}

_CENTENAS = {
    100: "cento",
    200: "duzentos",
    300: "trezentos",
    400: "quatrocentos",
    500: "quinhentos",
    600: "seiscentos",
    700: "setecentos",
    800: "oitocentos",
    900: "novecentos",
}


def _normalizar_decimal(valor):
    if isinstance(valor, str):
        valor = valor.replace("R$", "").replace("r$", "")
        valor = valor.replace(" ", "").strip()
        if "," in valor:
            valor = valor.replace(".", "").replace(",", ".")
        elif valor.count(".") > 1:
            valor = valor.replace(".", "")
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _numero_ate_999_por_extenso(numero):
    numero = int(numero)
    if numero < 20:
        return _UNIDADES[numero]
    if numero < 100:
        dezena = (numero // 10) * 10
        resto = numero % 10
        if not resto:
            return _DEZENAS[dezena]
        return f"{_DEZENAS[dezena]} e {_UNIDADES[resto]}"
    if numero == 100:
        return "cem"

    centena = (numero // 100) * 100
    resto = numero % 100
    if not resto:
        return _CENTENAS[centena]
    return f"{_CENTENAS[centena]} e {_numero_ate_999_por_extenso(resto)}"


def _numero_por_extenso(numero):
    numero = int(numero)
    if numero < 1000:
        return _numero_ate_999_por_extenso(numero)
    if numero < 1_000_000:
        milhares = numero // 1000
        resto = numero % 1000
        prefixo = "mil" if milhares == 1 else f"{_numero_ate_999_por_extenso(milhares)} mil"
        if not resto:
            return prefixo
        conector = " e " if resto < 100 or resto % 100 == 0 else " "
        return f"{prefixo}{conector}{_numero_ate_999_por_extenso(resto)}"
    return str(numero)


def _moeda_unidade(valor, singular, plural):
    return singular if int(valor) == 1 else plural


def valor_por_extenso_ptbr(valor):
    try:
        valor_decimal = _normalizar_decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return "(preencher manualmente)"

    if valor_decimal < 0:
        return f"menos {valor_por_extenso_ptbr(abs(valor_decimal))}"

    centavos_total = int((valor_decimal * 100).to_integral_value(rounding=ROUND_HALF_UP))
    reais = centavos_total // 100
    centavos = centavos_total % 100

    partes = [f"{_numero_por_extenso(reais)} {_moeda_unidade(reais, 'real', 'reais')}"]
    if centavos:
        partes.append(
            f"{_numero_por_extenso(centavos)} {_moeda_unidade(centavos, 'centavo', 'centavos')}"
        )
    return " e ".join(partes)
