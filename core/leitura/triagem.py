"""Para qual módulo vai um e-mail: coffee break, imprensa, publicações, evento social ou palestra.

Pontuação por sinais no assunto (vale o dobro), no corpo, na assinatura e
no domínio do remetente. A tela mostra os dois melhores para o usuário
confirmar; nada é decidido sozinho. Puro: não consulta banco.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .datas import dobrar

__all__ = ["Destino", "MODULOS", "triar", "triar_mensagem"]

MODULOS = {
    "coffee_break": "Coffee break",
    "atendimento_imprensa": "Atendimento à imprensa",
    "publicacoes": "Publicações",
    "solicitacoes": "Evento social",
    "demandas_eventos": "Palestras e eventos",
}

# (expressão no texto dobrado, peso, rótulo do sinal)
_SINAIS: dict[str, list[tuple[re.Pattern, float, str]]] = {
    "coffee_break": [
        (re.compile(r"\bcof+e+\b|\bcof+e+[\s-]?break\b"), 3, "coffee break"),
        (re.compile(r"\bcafe\b"), 1.5, "café"),
        (re.compile(r"\bkits?\s+(?:de\s+)?lanches?\b|\blanches?\b"), 2, "lanche"),
        (re.compile(r"\bsalgad(?:o|os|inhos)\b"), 1.5, "salgados"),
        (re.compile(r"\bbuffet\b|\bcoquetel\b"), 1, "buffet"),
    ],
    "atendimento_imprensa": [
        (re.compile(r"\bentrevistas?\b"), 2, "entrevista"),
        (re.compile(r"\bposicionamento\b"), 2, "posicionamento"),
        (re.compile(r"\bnota\b(?!\s+fiscal)|\bnota\s+oficial\b"), 1, "nota"),
        (re.compile(r"\bdeadline\b"), 2, "deadline"),
        (re.compile(r"\bmaterias?\b|\breportage[mn]s?\b"), 1.5, "matéria"),
        (re.compile(r"\bimprensa\b"), 1, "imprensa"),
        (re.compile(r"\bsonora\b|\bvai\s+ao\s+ar\b|\bfechamento\s+da\s+(?:edicao|materia)\b"), 1.5, "fechamento"),
    ],
    "publicacoes": [
        (re.compile(r"\breleases?\b"), 3, "release"),
        (re.compile(r"\bpara\s+(?:a\s+)?divulgacao\b|\bdivulgar\b"), 2, "para divulgação"),
        (re.compile(r"\boperac(?:ao|oes)\b"), 1.5, "operação"),
        (re.compile(r"\bpris(?:ao|oes)\b|\bpres[oa]s?\b|\bflagrante\b"), 1.5, "prisão"),
        (re.compile(r"\bmandados?\b"), 1.5, "mandado"),
        (re.compile(r"\bapreens(?:ao|oes)\b|\bapreendid[oa]s?\b"), 1, "apreensão"),
    ],
    "solicitacoes": [
        (re.compile(r"\bcin\b|\brg\b|\bcarteiras?\s+de\s+identidade\b|\bidentidade\b"), 2, "RG/CIN"),
        (re.compile(r"\bemiss(?:ao|oes)\s+d[aeo]s?\s+(?:cin|rg|carteiras?|documentos?|identidade|nova\s+identidade)\b"), 3, "emissão de identidade"),
        (re.compile(r"\bidentificacao\s+civil\b|\binstituto\s+de\s+identificacao\b|\biipr\b"), 3, "identificação civil"),
        (re.compile(r"\bposto\s+(?:movel|de\s+atendimento)\b|\batendimento\s+in\s+loco\b|\bkits?\s+biometric"), 2, "posto de atendimento"),
        (re.compile(r"\bcrianca\s+e\s+adolescente\s+protegidos\b"), 3, "Criança e Adolescente Protegidos"),
        (re.compile(r"\bunidade\s+movel\b|\bonibus\b|\bcarreta\b"), 3, "unidade móvel"),
        (re.compile(r"\bparana\s+em\s+acao\b"), 3, "Paraná em Ação"),
        (re.compile(r"\bjustica\s+no\s+bairro\b"), 3, "Justiça no Bairro"),
        (re.compile(r"\bmutirao\b"), 2, "mutirão"),
        (re.compile(r"\bacao\s+social\b|\bacao\s+de\s+cidadania\b"), 2, "ação social"),
        (re.compile(r"\bfeiras?\b"), 1, "feira"),
        (re.compile(r"\bemissao\s+de\s+documentos\b|\bcoleta\s+de\s+digitais\b|\bbiometria\b"), 2, "emissão de documentos"),
    ],
    "demandas_eventos": [
        (re.compile(r"\bpalestras?\b"), 3, "palestra"),
        (re.compile(r"\bescolas?\b|\bcolegios?\b"), 1.5, "escola"),
        (re.compile(r"\balun[oa]s?\b|\bestudantes\b"), 1.5, "alunos"),
        (re.compile(r"\bpcpr\s+na\s+comunidade\b"), 3, "PCPR na Comunidade"),
        (re.compile(r"\bbate[\s-]?papo\b|\broda\s+de\s+conversa\b"), 2, "bate-papo"),
        (re.compile(r"\bconscientizacao\b|\borientacao\s+sobre\b"), 1, "conscientização"),
        (re.compile(r"\btemas?\b"), 0.5, "tema"),
    ],
}

# Domínio de veículo de imprensa (os mais comuns no Paraná e os genéricos).
_R_DOMINIO_IMPRENSA = re.compile(
    r"@(?:[\w-]+\.)*(?:globo|g1|rpc|rpctv|band|bandab|bandnews|sbt|record|r7|ric|ricmais|gazetadopovo|"
    r"tribunapr|bemparana|cbn|jovempan|uol|folha|folhadelondrina|estadao|cnnbrasil|metropoles|plural|"
    r"massa|paranaportal|tnonline|arede|diariodoscampos|odiario|cgn|catve|lance|terra|ig|bandnewsfm|"
    r"[\w-]*(?:jornal|radio|tv|news|noticias|portal|revista|gazeta|diario|tribuna|folha)[\w-]*)"
    r"\.(?:com|jor|net|org|tv|radio|info)(?:\.br)?\b"
)
_R_ASSINATURA_IMPRENSA = re.compile(
    r"\b(?:reporter|produtor[a]?|produc[ao]|redacao|jornalista|editor[a]?|pauteir[oa]|chefe\s+de\s+reportagem|"
    r"assessoria\s+de\s+imprensa|apresentador[a]?)\b"
)
_R_REMETENTE_PCPR = re.compile(r"@(?:[\w-]+\.)*(?:pc|policiacivil)\.pr\.gov\.br$")


@dataclass(frozen=True)
class Destino:
    """Um módulo candidato, com os pontos, a confiança (0 a 1) e os sinais achados."""

    modulo: str
    rotulo: str
    pontos: float
    confianca: float
    sinais: tuple[str, ...]


def triar(
    *,
    assunto: str = "",
    corpo: str = "",
    assinatura: str = "",
    remetente_email: str = "",
    modulos: Iterable[str] | None = None,
    extras: dict[str, list[tuple[float, str]]] | None = None,
) -> list[Destino]:
    """Os módulos candidatos, do mais provável ao menos provável (só os com pontos).

    `modulos` limita aos módulos que o usuário acessa. `extras` são pontos de
    fora do texto — {modulo: [(pontos, sinal), ...]} — como a memória dos
    pedidos anteriores do mesmo remetente. A confiança do primeiro cai
    quando o segundo está perto ou quando há poucos sinais.
    """
    permitidos = set(modulos) if modulos is not None else set(MODULOS)
    assunto_d, corpo_d, assinatura_d = dobrar(assunto), dobrar(corpo), dobrar(assinatura)
    email = (remetente_email or "").strip().lower()
    pontos: dict[str, float] = {}
    sinais: dict[str, list[str]] = {}

    def somar(modulo, valor, sinal):
        pontos[modulo] = pontos.get(modulo, 0) + valor
        sinais.setdefault(modulo, []).append(sinal)

    for modulo, regras in _SINAIS.items():
        for regex, peso, rotulo in regras:
            if regex.search(assunto_d):
                somar(modulo, 2 * peso, f"{rotulo} (assunto)")
            elif regex.search(corpo_d):
                somar(modulo, peso, rotulo)
    if email and _R_DOMINIO_IMPRENSA.search(email):
        somar("atendimento_imprensa", 4, "remetente de veículo de imprensa")
    if _R_ASSINATURA_IMPRENSA.search(assinatura_d):
        somar("atendimento_imprensa", 3, "assinatura de jornalista")
    if email and _R_REMETENTE_PCPR.search(email) and pontos.get("publicacoes"):
        somar("publicacoes", 2, "remetente da PCPR")
    for modulo, itens in (extras or {}).items():
        for valor, sinal in itens:
            if modulo in MODULOS and valor:
                somar(modulo, valor, sinal)

    candidatos = sorted(
        ((m, p) for m, p in pontos.items() if p > 0 and m in permitidos), key=lambda c: -c[1]
    )
    total = sum(p for _, p in candidatos)
    destinos = []
    for posicao, (modulo, valor) in enumerate(candidatos):
        segundo = candidatos[posicao + 1][1] if posicao + 1 < len(candidatos) else 0
        margem = valor / (valor + segundo) if posicao == 0 else valor / total
        forca = min(1.0, valor / 6)
        destinos.append(Destino(modulo, MODULOS[modulo], round(valor, 2), round(margem * forca, 2), tuple(sinais[modulo])))
    return destinos


def triar_mensagem(mensagem, *, modulos: Iterable[str] | None = None, extras=None) -> list[Destino]:
    """`triar` a partir de uma `Mensagem` já lida (mensagem.py)."""
    return triar(
        assunto=mensagem.assunto_limpo,
        corpo=mensagem.corpo,
        assinatura=mensagem.assinatura,
        remetente_email=mensagem.remetente_email,
        modulos=modulos,
        extras=extras,
    )
