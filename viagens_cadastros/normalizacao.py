"""Normalização e máscaras dos cadastros de viagens.

Os cadastros de viagens guardam o dado **cru e normalizado** (só dígitos no CPF,
placa sem hífen, nome em maiúsculas) e formatam apenas na exibição. Assim a
unicidade vale sobre o dado real: "410.123.456-78" e "41012345678" não podem
virar dois servidores diferentes.
"""

import re

RG_NAO_POSSUI = "NAO POSSUI RG"
RG_NAO_POSSUI_EXIBICAO = "NÃO POSSUI RG"
VAZIO = "—"

PLACA_ANTIGA = re.compile(r"^[A-Z]{3}[0-9]{4}$")
PLACA_MERCOSUL = re.compile(r"^[A-Z]{3}[0-9][A-Z][0-9]{2}$")


def normalizar_espacos(valor):
    return " ".join((valor or "").strip().split())


def normalizar_maiusculas(valor):
    return normalizar_espacos(valor).upper()


def normalizar_digitos(valor):
    return "".join(caractere for caractere in (valor or "") if caractere.isdigit())


def normalizar_placa(valor):
    return re.sub(r"[^A-Z0-9]", "", (valor or "").upper())


def normalizar_rg(valor):
    """Só letras e números, em maiúsculas — o RG não tem formato único no país."""
    return "".join(c for c in (valor or "").upper() if c.isalnum())


def placa_valida(placa):
    placa = (placa or "").strip()
    if len(placa) != 7:
        return False
    return bool(PLACA_ANTIGA.match(placa) or PLACA_MERCOSUL.match(placa))


def cpf_valido(cpf):
    """CPF com 11 dígitos e dígitos verificadores corretos."""
    cpf = normalizar_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    if int(cpf[9]) != (soma * 10 % 11) % 10:
        return False
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    return int(cpf[10]) == (soma * 10 % 11) % 10


def formatar_cpf(valor):
    digitos = normalizar_digitos(valor)
    if len(digitos) != 11:
        return valor or ""
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def formatar_telefone(valor):
    digitos = normalizar_digitos(valor)
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    return valor or ""


def formatar_rg(valor):
    texto = (valor or "").strip()
    if not texto:
        return ""
    if texto.upper() == RG_NAO_POSSUI:
        return RG_NAO_POSSUI_EXIBICAO
    digitos = normalizar_digitos(texto)
    if len(digitos) == 8:
        return f"{digitos[0]}.{digitos[1:4]}.{digitos[4:7]}-{digitos[7]}"
    if len(digitos) == 9:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}-{digitos[8]}"
    return texto


def formatar_placa(valor):
    placa = normalizar_placa(valor)
    if PLACA_ANTIGA.match(placa):
        return f"{placa[:3]}-{placa[3:]}"
    return placa or (valor or "")


def exibir(valor, formatador=None):
    """Valor formatado para tela, ou um travessão quando vazio."""
    texto = (valor or "").strip()
    if not texto:
        return VAZIO
    return (formatador(texto) if formatador else texto) or VAZIO
