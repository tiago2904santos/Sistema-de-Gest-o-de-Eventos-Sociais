"""Registro dos blocos documentais e dos pontos de quebra, por tipo.

Bloco documental é parágrafo do modelo — não nasce de campo algum do
ofício. O texto padrão mora aqui, e só aqui: o template o renderiza pela
tag `{% bloco "chave" %}`, e o override gravado em `DocumentoBloco` vale no
lugar dele. Ponto de quebra é o lugar onde o template admite uma quebra de
página (`{% ponto_de_quebra "chave" %}`); a quebra em si é um bloco do tipo
`quebra_pagina` gravado para essa chave. Quebra fora de um ponto registrado
não existe — é o que mantém a quebra um elemento controlado.
"""

from __future__ import annotations

from dataclasses import dataclass

from documentos.services.types import DocumentoTipo


@dataclass(frozen=True)
class BlocoDocumental:
    chave: str
    rotulo: str
    padrao: str
    ajuda: str = ""


@dataclass(frozen=True)
class PontoDeQuebra:
    chave: str
    rotulo: str


BLOCOS_OFICIO = (
    BlocoDocumental(
        "declaracao_cartao", "Declaração do cartão corporativo",
        "Declaro que os servidores estão cientes da necessidade de estar na posse de cartão corporativo "
        "vigente e apto para uso, no período do deslocamento.",
        ajuda="Parágrafo do modelo, não de um campo do ofício. O texto alterado vale só para este documento.",
    ),
)

QUEBRAS_OFICIO = (
    PontoDeQuebra("apos_equipe", "Depois da tabela da equipe"),
    PontoDeQuebra("apos_roteiro", "Depois do roteiro"),
    PontoDeQuebra("apos_transporte", "Depois do transporte"),
    PontoDeQuebra("antes_assinatura", "Antes da assinatura"),
)

REGISTRO_BLOCOS: dict[DocumentoTipo, dict[str, BlocoDocumental]] = {
    DocumentoTipo.OFICIO: {bloco.chave: bloco for bloco in BLOCOS_OFICIO},
}
REGISTRO_QUEBRAS: dict[DocumentoTipo, dict[str, PontoDeQuebra]] = {
    DocumentoTipo.OFICIO: {ponto.chave: ponto for ponto in QUEBRAS_OFICIO},
}


def blocos_do_tipo(tipo) -> dict[str, BlocoDocumental]:
    return REGISTRO_BLOCOS.get(tipo, {})


def bloco(tipo, chave: str) -> BlocoDocumental | None:
    return blocos_do_tipo(tipo).get(chave)


def quebras_do_tipo(tipo) -> dict[str, PontoDeQuebra]:
    return REGISTRO_QUEBRAS.get(tipo, {})


def ponto_de_quebra(tipo, chave: str) -> PontoDeQuebra | None:
    return quebras_do_tipo(tipo).get(chave)
