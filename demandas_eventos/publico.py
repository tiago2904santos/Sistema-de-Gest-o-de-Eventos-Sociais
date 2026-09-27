"""Quantas pessoas a palestra terá ("cerca de 200 alunos", "Público: 130 motoristas").

A leitura genérica (`core.leitura.casamento.quantidade_de_pessoas`) conhece
os públicos dos eventos em geral; palestra fala de mulheres, pais,
motoristas, líderes, empresários… Aqui a lista é a das palestras, e o
número não atravessa linha (o "km 212" da linha de cima não é o público).

Fica de fora o que não é número declarado: "3 turmas de 35" (a conta é de
quem lê), "km 212", "nº 45".
"""

from __future__ import annotations

import re

from core.leitura.casamento import Achado
from core.leitura.datas import dobrar

# Plural e singular ("umas 40 mulher"), sem acento.
_GENTE = (
    "pessoas?", "participantes?", "convidad[oa]s?", "servidor(?:es|as?)?", "alun[oa]s?", "estudantes?",
    "criancas?", "jovens?", "adolescentes?", "idos[oa]s?", "professor(?:es|as?)?", "colaborador(?:es|as?)?",
    "integrantes?", "inscritos?", "ouvintes?", "familias?", "moradores?", "membros?", "funcionari[oa]s?",
    "mulher(?:es)?", "homens?", "pais", "maes", "empresari[oa]s?", "lideres?", "gerentes?", "motoristas?",
    "associad[oa]s?", "cooperad[oa]s?", "diretor(?:es|as?)?", "academicos?", "universitari[oa]s?",
    "trabalhador(?:es|as?)?", "agentes?", "policiais", "vigilantes?", "agricultor(?:es|as?)?",
    "produtor(?:es|as?)?", "cuidador(?:es|as?)?", "desbravador(?:es|as?)?", "fieis", "frequentador(?:es|as?)?",
    "conselheir[oa]s?", "educador(?:es|as?)?", "pedagog[oa]s?", "gestor(?:es|as?)?", "lojistas?",
    "comerciantes?", "catequistas?", "casais", "voluntari[oa]s?", "atletas?", "internos?", "detentos?",
    "pacientes?", "usuari[oa]s?", "beneficiari[oa]s?", "profissionais", "adultos?", "caminhoneiros?",
    "vendedor(?:es|as?)?", "operador(?:es|as?)?", "cadetes?", "vereador(?:es|as?)?", "guardas?",
    "enfermeir[oa]s?", "tecnic[oa]s?", "idosas?", "senhoras?", "gestantes?", "responsaveis",
)
_NUMERO = (
    r"(?<![\d.,/])(?P<n>\d{1,3}(?:\.\d{3})+|\d{1,6})(?P<mil>\s+mil\b)?"
    r"(?![\d/]|[.,:]\d|\s*h\b|\s*(?:%|reais|anos|dias|horas|min))"
)
_R_DIRETA = re.compile(
    _NUMERO + r"[ \t]*(?:\([^)\n]{1,40}\)[ \t]*)?"
    r"(?:(?!de\b|do\b|da\b|para\b|e\b|a\b|o\b|com\b|em\b|no\b|na\b|por\b)[a-z]{3,}[ \t]+)?"
    r"(?:" + "|".join(_GENTE) + r")\b"
)
_R_ANCORADA = re.compile(
    r"\b(?:publico(?:[ \t]+(?:estimado|previsto|esperado|alvo|total|circulante))*|quantidade(?:[ \t]+de[ \t]+"
    r"(?:pessoas|participantes|publico))?|(?:numero|n[o.]?|qtde?\.?)[ \t]+de[ \t]+(?:participantes|pessoas|alunos|"
    r"convidados|publico)|total[ \t]+de[ \t]+(?:participantes|pessoas)|estimativa(?:[ \t]+de[ \t]+publico)?)"
    r"[ \t]*(?:de|:|-|=|e[ \t]+de|:[ \t]*de)?[ \t]*"
    r"(?:cerca[ \t]+de|aproximadamente|aprox\.?|em[ \t]+torno[ \t]+de|ate|mais[ \t]+de|uns|umas)?[ \t]*" + _NUMERO
)
# O número que é conta de turmas, quilômetro, número de endereço ou de documento.
_R_ANTES_NAO = re.compile(r"(?:\bturmas?[ \t]+(?:de|com)|\bgrupos?[ \t]+de|\bkm|\bn[o.º°]|\bnumero|,)[ \t]*$")


def _achados(texto: str):
    dobrado = dobrar(texto)
    for regex in (_R_DIRETA, _R_ANCORADA):
        for m in regex.finditer(dobrado):
            if regex is _R_DIRETA and _R_ANTES_NAO.search(dobrado[max(0, m.start("n") - 20):m.start("n")]):
                continue
            valor = int(m.group("n").replace(".", "")) * (1000 if m.group("mil") else 1)
            if 0 < valor <= 100000:
                yield valor, m.start(), m.end()


def publico_no_texto(texto: str) -> Achado | None:
    """O público declarado; havendo vários, o maior (o total costuma ser o maior)."""
    texto = texto or ""
    achados = list(_achados(texto))
    if not achados:
        return None
    valor, inicio, fim = max(achados, key=lambda a: (a[0], -a[1]))
    trecho = " ".join(texto[max(0, inicio - 60):fim + 40].split())
    return Achado(valor, str(valor), trecho, "M")
