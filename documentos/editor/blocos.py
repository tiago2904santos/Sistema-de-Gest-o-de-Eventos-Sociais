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
    # Marcadores que o texto aceita (`{periodo}`...), preenchidos com os dados
    # do documento; a tela de modelos os lista (m057).
    campos: tuple[str, ...] = ()


@dataclass(frozen=True)
class PontoDeQuebra:
    chave: str
    rotulo: str


BLOCOS_OFICIO = (
    BlocoDocumental(
        "secretaria", "Linha da secretaria no cabeçalho",
        "SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA",
        ajuda="Texto do modelo. O texto alterado vale só para este documento.",
    ),
    BlocoDocumental(
        "abertura", "Abertura do ofício",
        "Senhor Delegado, através deste, solicito {assunto} e medidas para a concessão de diárias e recursos "
        "para combustível, conforme cronograma abaixo:",
        ajuda="Texto do modelo. {assunto} vira \"autorização\" ou \"convalidação\", conforme a data do ofício e a "
              "primeira saída do roteiro. O texto alterado vale só para este documento.",
        campos=("assunto",),
    ),
    BlocoDocumental(
        "fecho", "Fecho", "Respeitosamente,",
        ajuda="Texto do modelo. O texto alterado vale só para este documento.",
    ),
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

_SO_ESTE = "Texto do modelo. O texto alterado vale só para este documento."
SECRETARIA = BLOCOS_OFICIO[0]


def _blocos(*pares):
    return (SECRETARIA,) + tuple(BlocoDocumental(chave, rotulo, padrao, ajuda=_SO_ESTE) for chave, rotulo, padrao in pares)


BLOCOS_TERMO = _blocos(
    ("titulo", "Título", "Termo de autorização para participação em eventos da ASCOM"),
) + (
    BlocoDocumental(
        "texto", "Texto da manifestação",
        "manifesto o interesse em participar do PCPR na Comunidade, {periodo}, no município de {destino} para "
        "execução de atividades inerentes à Assessoria de Comunicação Social - ASCOM/PCPR.",
        ajuda="O parágrafo principal do termo, depois da identificação do servidor. {periodo} e {destino} saem em "
              "negrito, com os dados do termo.",
        campos=("periodo", "destino", "servidor", "unidade"),
    ),
) + _blocos(
    ("declaracao", "Declaração do cartão corporativo",
     "Declaro que estou ciente da necessidade de estar na posse de cartão corporativo vigente e apto para uso, "
     "no período do deslocamento."),
    ("assinatura_servidor", "Assinatura do servidor", "Assinatura servidor:"),
    ("assinatura_chefia", "Autorização da chefia", "Autorização da Chefia:"),
)[1:]  # sem repetir a linha da secretaria

BLOCOS_JUSTIFICATIVA = _blocos(("titulo", "Título", "Justificativa"))

BLOCOS_ORDEM = _blocos(
    ("atribuicoes", "Atribuições de quem determina",
     "da Polícia Civil do Paraná, no uso das atribuições que me foram conferidas pelo Delegado-Geral "
     "Silvio Jacob Rockembach, bem como pelo Conselho da Polícia Civil,"),
    ("determino", "Determino", "Determino"),
)

BLOCOS_PLANO = _blocos(
    ("secao_contextualizacao", "Título: contextualização", "Breve contextualização"),
    ("secao_atuacao", "Título: atuação", "Atuação"),
    ("secao_atividades", "Título: atividades", "Atividades a serem desenvolvidas"),
    ("secao_metas", "Título: metas", "Metas estabelecidas"),
    ("secao_recursos", "Título: recursos", "Recursos necessários"),
    ("secao_valor", "Título: valor", "Valor total do plano"),
    ("secao_coordenador", "Título: coordenador", "Coordenador do evento"),
    ("secao_consideracoes", "Título: considerações", "Considerações finais"),
)

BLOCOS_RELATORIO = _blocos(
    ("titulo", "Título", "Relatório técnico de viagem"),
    ("titulo_valores", "Título dos valores", "Valores utilizados na viagem:"),
    ("declaracao", "Declaração",
     "Declaramos que o trabalho previsto na programação de viagem foi realizado, assim como cumprido o período "
     "de realização da viagem e a documentação encaminhada ao setor responsável"),
)

BLOCOS_DIARIO = (SECRETARIA,)

REGISTRO_BLOCOS: dict[DocumentoTipo, dict[str, BlocoDocumental]] = {
    tipo: {bloco.chave: bloco for bloco in blocos}
    for tipo, blocos in (
        (DocumentoTipo.OFICIO, BLOCOS_OFICIO),
        (DocumentoTipo.TERMO_AUTORIZACAO, BLOCOS_TERMO),
        (DocumentoTipo.JUSTIFICATIVA, BLOCOS_JUSTIFICATIVA),
        (DocumentoTipo.ORDEM_SERVICO, BLOCOS_ORDEM),
        (DocumentoTipo.PLANO_TRABALHO, BLOCOS_PLANO),
        (DocumentoTipo.RELATORIO_TECNICO, BLOCOS_RELATORIO),
        (DocumentoTipo.DIARIO_BORDO, BLOCOS_DIARIO),
    )
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
