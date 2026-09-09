"""Leitura de valores monetários digitados por pessoas.

O inverso de ``documentos.services.formatters.format_currency_br``. Existe
porque o sistema tem um campo onde o operador escreve o valor que o servidor
efetivamente recebeu, e até agora esse texto ia direto para um documento
assinado sem ninguém conferir se era um número (``NOVO-10``).

O separador é o brasileiro: vírgula decide os centavos. Um ponto seguido de
três dígitos é milhar (``1.500``); seguido de um ou dois, é decimal (``80.00``,
que é como muita gente digita em teclado numérico).

A função devolve **valor e anotação** porque o campo real carrega as duas
coisas: ``"R$80,00 (saque)"`` é oitenta reais mais a explicação de por que o
valor difere do liberado. Separar os dois permite validar o número sem perder
o texto — e permite remontar a mesma string no documento.
"""

from __future__ import annotations

import re
from decimal import Decimal
from decimal import InvalidOperation

__all__ = [
    "parse_valor_monetario",
    "converter_valor_legado",
    "ValorMonetarioInvalido",
]


class ValorMonetarioInvalido(ValueError):
    """O texto não começa por um valor monetário reconhecível."""


# R$ opcional, milhares com ponto opcionais, decimais com vírgula ou ponto.
_PADRAO = re.compile(
    r"""
    ^\s*
    (?:R\$)?\s*
    (?P<inteiro>\d{1,3}(?:\.\d{3})+|\d+)
    (?:[,.](?P<centavos>\d{1,2}))?
    \s*
    (?P<resto>.*)$
    """,
    re.VERBOSE | re.IGNORECASE | re.DOTALL,
)


def parse_valor_monetario(texto: object) -> tuple[Decimal | None, str]:
    """Devolve ``(valor, anotação)`` a partir do texto digitado.

    Texto vazio devolve ``(None, "")`` — ausência não é erro; o campo é
    opcional e vazio significa "usar o valor padrão".

    Levanta ``ValorMonetarioInvalido`` quando há texto mas nenhum número
    reconhecível no começo (``"abc"``), ou quando o que sobra depois do número
    começa com dígito ou vírgula (``"350,00,00"``) — sinal de que o número foi
    digitado errado, e não de que existe uma anotação.
    """
    bruto = str(texto or "").strip()
    if not bruto:
        return None, ""

    match = _PADRAO.match(bruto)
    if match is None:
        raise ValorMonetarioInvalido(bruto)

    resto = match.group("resto").strip()
    if resto[:1].isdigit() or resto[:1] in {",", "."}:
        raise ValorMonetarioInvalido(bruto)

    inteiro = match.group("inteiro").replace(".", "")
    centavos = (match.group("centavos") or "").ljust(2, "0")
    try:
        valor = Decimal(f"{inteiro}.{centavos or '00'}")
    except InvalidOperation as exc:  # pragma: no cover - regex já garante dígitos
        raise ValorMonetarioInvalido(bruto) from exc

    return valor, resto


def converter_valor_legado(texto: object) -> tuple[Decimal | None, str]:
    """Decide o destino de um valor que já estava gravado como texto livre.

    Regra única, usada pela migração do ``NOVO-10`` e testável sem subir o
    maquinário de migração:

    * texto que vira número positivo → ``(valor, anotação)``;
    * qualquer outra coisa → ``(None, texto_original)``.

    O segundo caso não descarta nada. Não dá para inventar um número que
    ninguém digitou, mas jogar fora o que a pessoa escreveu seria pior: o
    documento volta a mostrar o valor padrão e o texto original fica visível
    para quem for corrigir.
    """
    bruto = str(texto or "").strip()
    if not bruto:
        return None, ""
    try:
        valor, anotacao = parse_valor_monetario(bruto)
    except ValorMonetarioInvalido:
        return None, bruto
    if valor is None or valor <= 0:
        return None, bruto
    return valor, anotacao
