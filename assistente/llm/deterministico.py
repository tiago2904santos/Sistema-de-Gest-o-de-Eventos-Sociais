"""Interpretador sem modelo de linguagem: regex ancorada no cadastro real.

Este é o adaptador padrão, e ele não custa nada para rodar. A ideia central:
em vez de tentar adivinhar onde termina um nome próprio com gramática, ele
**pergunta ao banco**. Para achar o destino em "evento em Santo Antônio da
Platina dia 18", pega as palavras seguintes à preposição e tenta resolver a
sequência mais longa primeiro — cinco palavras, quatro, três — até o cadastro
de municípios reconhecer uma. Nome com "da", "de" e "dos" funciona porque
quem decide onde ele termina é a tabela, não a regra.

O mesmo vale para servidores. É por isso que este adaptador acerta os casos
do dia a dia sem nenhuma inteligência: os nomes que importam já estão no
sistema, e o que não está no sistema não deveria mesmo ser aceito.

Quando um adaptador remoto estiver configurado, ele assume — mas este
continua sendo o caminho de queda quando a API falha ou a chave sai do ar.
"""

from __future__ import annotations

import re

from core.normalizers import normalize_spaces, remove_accents

from .. import periodos
from ..resolucao import NENHUM, resolver_municipio, resolver_servidor
from .base import AdaptadorLLM, Intencao

# Até onde vale a pena procurar um nome próprio depois da preposição.
MAXIMO_PALAVRAS_NOME = 5

GATILHOS_PENDENCIA = r"pend|parad|atrasad|falta|em aberto|nao enviou|sem km"
GATILHOS_PREPARO = r"\b(faz|faca|fazer|crie|criar|cria|monte|montar|monta|prepare|preparar|prepara|gere|gerar|abra|abrir)\b"
GATILHOS_QUEM = r"\b(quem|quais servidores|que servidores)\b"
GATILHOS_VIAGEM = r"\b(viagem|viagens|deslocament)"


def _chave(texto: str) -> str:
    return remove_accents(normalize_spaces(texto or "")).lower()


def _palavras_apos(texto: str, padrao: str) -> list[str]:
    """As palavras que vêm depois de um marcador, em bruto e com acento."""
    achado = re.search(padrao, texto, flags=re.IGNORECASE)
    if not achado:
        return []
    resto = texto[achado.end():]
    # Vírgula e ponto terminam o trecho: "Maringá, dia 18" não é um município
    # chamado "Maringá dia 18".
    resto = re.split(r"[,.;]", resto)[0]
    return [p for p in re.split(r"\s+", resto.strip()) if p]


# Artigo antes do nome ("vai *o* João") não faz parte do nome e atrapalha o
# casamento, porque o cadastro guarda "JOÃO SILVA", não "O JOÃO SILVA".
ARTIGOS = {"o", "a", "os", "as", "um", "uma", "uns", "umas"}
RUIDO = ARTIGOS | {"dia", "com", "e", "no", "na", "de", "do", "da"}


def _maior_casamento(palavras: list[str], resolver) -> tuple[object | None, int]:
    """A sequência mais longa que o cadastro reconhece, e quantas palavras usou.

    Devolve também quantas palavras consumiu — incluindo os artigos descartados
    no começo — para quem varre uma frase com vários nomes seguidos.
    """
    descartadas = 0
    while palavras and _chave(palavras[0]) in ARTIGOS:
        palavras = palavras[1:]
        descartadas += 1

    for tamanho in range(min(MAXIMO_PALAVRAS_NOME, len(palavras)), 0, -1):
        candidato = " ".join(palavras[:tamanho])
        # Palavra que é claramente outra coisa não vira nome próprio.
        if _chave(candidato) in RUIDO:
            continue
        resolucao = resolver(candidato)
        if resolucao.status != NENHUM:
            return resolucao, tamanho + descartadas
    return None, 0


def _extrair_municipio(texto: str):
    for padrao in (
        r"\b(?:para|pra|pro)\s+(?:o\s+|a\s+)?",
        r"\bevento\s+em\s+",
        r"\bem\s+",
        r"\bno\s+municipio\s+de\s+",
    ):
        resolucao, _ = _maior_casamento(_palavras_apos(texto, padrao), resolver_municipio)
        if resolucao is not None:
            return resolucao
    return None


# Palavras que marcam o fim de um nome de lugar numa frase solta.
FIM_DE_LUGAR = {"dia", "em", "no", "na", "com", "para", "pra", "pro", "vai", "vao", "e"}


def _destino_bruto(texto: str) -> str:
    """O que a pessoa chamou de destino, mesmo que o cadastro não conheça.

    Serve para a resposta poder dizer "não encontrei o município X" em vez de
    "não entendi" — a diferença entre saber que o cadastro está incompleto e
    achar que o assistente está quebrado.
    """
    for padrao in (r"\bevento\s+em\s+", r"\b(?:para|pra|pro)\s+(?:o\s+|a\s+)?", r"\bem\s+"):
        palavras = _palavras_apos(texto, padrao)
        while palavras and _chave(palavras[0]) in ARTIGOS:
            palavras = palavras[1:]
        nome = []
        for palavra in palavras[:3]:
            if _chave(palavra) in FIM_DE_LUGAR or any(c.isdigit() for c in palavra):
                break
            nome.append(palavra)
        if nome:
            return " ".join(nome)
    return ""


def _extrair_pessoas(texto: str) -> list[str]:
    """Nomes ditos como quem viaja — sem o motorista, que tem marcador próprio."""
    nomes = []
    for padrao in (r"\b(?:vai|vao|vão|vao\s+o|leva|levando|com\s+o\s+servidor)\s+", r"\bservidores?\s+"):
        palavras = _palavras_apos(texto, padrao)
        while palavras:
            resolucao, usadas = _maior_casamento(palavras, resolver_servidor)
            if resolucao is None:
                break
            nomes.append(resolucao.termo)
            palavras = palavras[usadas:]
            # "Fulano e Beltrano": o "e" liga dois nomes na mesma frase.
            if palavras and _chave(palavras[0]) in {"e", "com"}:
                palavras = palavras[1:]
            else:
                break
        if nomes:
            break
    return nomes


def _pessoas_brutas(texto: str) -> list[str]:
    """O nome dito para "quem vai", mesmo sem casamento no cadastro.

    Descartar em silêncio um nome que a pessoa falou é o pior desfecho
    possível: ela veria o resumo sem aquele servidor e poderia não notar.
    Melhor o assistente dizer que não achou e pedir o nome completo.
    """
    for padrao in (r"\b(?:vai|vao|v\u00e3o|leva|levando)\s+",):
        palavras = _palavras_apos(texto, padrao)
        while palavras and _chave(palavras[0]) in ARTIGOS:
            palavras = palavras[1:]
        nome = []
        for palavra in palavras[:3]:
            if _chave(palavra) in RUIDO or any(c.isdigit() for c in palavra):
                break
            nome.append(palavra)
        if nome:
            return [" ".join(nome)]
    return []


def _extrair_motorista(texto: str) -> str:
    palavras = _palavras_apos(texto, r"\bmotorista\s+(?:o\s+|a\s+)?")
    resolucao, _ = _maior_casamento(palavras, lambda t: resolver_servidor(t))
    return resolucao.termo if resolucao is not None else ""


class InterpretadorDeterministico(AdaptadorLLM):
    nome = "deterministico"
    remoto = False

    def interpretar(self, texto: str, *, ferramentas, usuario) -> Intencao:
        alvo = _chave(texto)
        disponiveis = {f.nome for f in ferramentas}
        inicio, fim = periodos.interpretar(texto)

        if re.search(GATILHOS_PENDENCIA, alvo) and "consultar_pendencias" in disponiveis:
            return Intencao(
                ferramenta="consultar_pendencias",
                explicacao="Pedido de pendências.",
            )

        if re.search(GATILHOS_PREPARO, alvo) and "preparar_viagem" in disponiveis:
            municipio = _extrair_municipio(texto)
            campos = {}
            if municipio is not None:
                campos["destino"] = municipio.termo
            if inicio:
                campos["data_inicio"] = inicio.isoformat()
                if fim and fim != inicio:
                    campos["data_fim"] = fim.isoformat()
            pessoas = _extrair_pessoas(texto) or _pessoas_brutas(texto)
            if pessoas:
                campos["servidores"] = ", ".join(pessoas)
            motorista = _extrair_motorista(texto)
            if motorista:
                campos["motorista"] = motorista
            return Intencao(
                ferramenta="preparar_viagem",
                campos=campos,
                explicacao="Pedido de montagem de viagem.",
            )

        if re.search(GATILHOS_QUEM, alvo) and "consultar_deslocamentos" in disponiveis:
            municipio = _extrair_municipio(texto)
            # Sem casamento no cadastro, vale o que foi dito: a ferramenta
            # responde nomeando o município que não existe.
            destino = municipio.termo if municipio is not None else _destino_bruto(texto)
            if destino:
                argumentos = {"destino": destino}
                if inicio:
                    argumentos["inicio"] = inicio.isoformat()
                    argumentos["fim"] = (fim or inicio).isoformat()
                return Intencao(
                    ferramenta="consultar_deslocamentos",
                    argumentos=argumentos,
                    explicacao="Pergunta sobre quem vai a um destino.",
                )

        if re.search(GATILHOS_VIAGEM, alvo) and "consultar_viagens" in disponiveis:
            argumentos = {}
            municipio = _extrair_municipio(texto)
            if municipio is not None:
                argumentos["destino"] = municipio.termo
            if inicio:
                argumentos["inicio"] = inicio.isoformat()
                argumentos["fim"] = (fim or inicio).isoformat()
            return Intencao(
                ferramenta="consultar_viagens",
                argumentos=argumentos,
                explicacao="Pergunta sobre viagens.",
            )

        return Intencao(explicacao="Não reconheci o pedido.")
