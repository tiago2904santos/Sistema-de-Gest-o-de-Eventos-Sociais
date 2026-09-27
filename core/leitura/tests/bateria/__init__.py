"""Bateria do preenchimento automático: e-mails fictícios com gabarito.

Cada caso é um e-mail inventado (nomes, telefones e endereços fictícios —
nenhum dado real entra aqui) e o que uma secretária atenta preencheria na
tela a partir dele. `avaliar.py` passa cada caso pelo leitor de verdade
(`core.leitura.mensagem` + o `preenchimento.py` do módulo + a triagem da
página inicial) e compara campo a campo; `test_bateria.py` exige zero erro.

Os casos moram em `casos_<modulo>.py`, cada um com:

- ``CADASTROS``: o que precisa existir no banco para o caso fazer sentido
  (temas, palestrantes, veículos, unidades, órgãos). Os municípios do PR e
  de SC (lista do IBGE, `municipios.json`), os tipos de evento e os
  serviços já vêm das migrações/da bateria;
- ``CASOS``: a lista de `Caso`.

Como escrever o gabarito (`esperado`), por campo:

- datas ``"2026-10-20"``, horas ``"09:00"``, números ``300``;
- cadastros pelo nome: ``"Ponta Grossa"`` (município), ``"PR"`` (estado),
  ``"Capacitação"`` (tipo), ``["Emissão de CIN", "Coleta de digitais"]``;
- texto livre: ``Contem("Ginásio Oscar Pereira")`` — o sugerido precisa
  conter isto (sem diferenciar acento e maiúscula);
- ``UmDe("a", "b")`` quando duas respostas são igualmente certas;
- ``AUSENTE``: o campo não pode ser preenchido (sugestão só "B", que a tela
  oferece sem preencher, é aceita). É o gabarito de "não invente": a data
  do envio não é a data do evento, o município da assinatura não é o do
  evento, e assim por diante.

Campos que o e-mail não permite saber ficam fora do `esperado` (não contam).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["AUSENTE", "Caso", "Contem", "UmDe"]


class _Ausente:
    def __repr__(self):
        return "AUSENTE"


AUSENTE = _Ausente()


@dataclass(frozen=True)
class Contem:
    """Texto livre: o sugerido precisa conter este trecho."""

    trecho: str


@dataclass(frozen=True)
class UmDe:
    """Mais de uma resposta certa."""

    opcoes: tuple

    def __init__(self, *opcoes):
        object.__setattr__(self, "opcoes", tuple(opcoes))


@dataclass(frozen=True)
class Caso:
    """Um e-mail e o gabarito.

    `formato`: ``"eml"`` (o texto é o arquivo .eml inteiro, com cabeçalhos
    RFC 822) ou ``"texto"`` (o que a pessoa colaria na tela: pode ter
    "De:/Enviado em:/Assunto:" do Outlook, uma conversa do WhatsApp…).
    `agora`: quando a pessoa lê o e-mail no sistema ("2026-09-24 10:00",
    horário de Brasília) — é a referência de "amanhã", "sexta que vem" e do
    ano que falta. `modulo`: a tela certa (a triagem precisa pôr em 1º).
    """

    id: str
    modulo: str
    formato: str
    agora: str
    texto: str
    esperado: dict = field(default_factory=dict)
    nota: str = ""
