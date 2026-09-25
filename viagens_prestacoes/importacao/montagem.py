"""Páginas do processo viram anexos: recorte, orientação e nome de arquivo.

Nada aqui grava: recebe bytes e devolve bytes. Quem guarda é `aplicacao`.

**Orientação.** Vem de `core.leitura.pdf`, que mede a direção do texto pela
matriz completa (a moldura do eProtocolo fora da votação) e grava o resultado
como `/Rotate` normalizado — o conteúdo da página não é tocado, então uma
assinatura digital embutida continua valendo e o cru pode ser guardado ao lado.
"""

from __future__ import annotations

import logging

from core.errors import capture

__all__ = ["diario_em_pe", "recortar_documento", "descrever_paginas", "rotacao_final"]


def rotacao_final(rotacao_planejada: int, giro: int) -> int:
    """O /Rotate gravado: o que a leitura decidiu mais o giro escolhido na conferência (↺ ↻)."""
    return (int(rotacao_planejada or 0) + int(giro or 0)) % 360


def recortar_documento(dados: bytes, paginas: list[int], rotacoes: dict[int, int] | None = None) -> bytes:
    """PDF só com as `paginas` do processo (índices a partir de 0), com o /Rotate de `rotacoes`.

    Sem `rotacoes`, as páginas saem como estão no processo — é o "cru" que fica em
    `arquivo_original`. O recorte não leva os metadados do volume (o /Author do
    eProtocolo é o CPF de quem baixou).
    """
    from core.leitura.pdf import recortar

    return recortar(dados, list(paginas), rotacoes or None)


def diario_em_pe(dados: bytes, *, exigir_paisagem: bool = False, ocr: bool = True) -> tuple[bytes, bool]:
    """(o diário com cada página em pé, se alguma página girou).

    O diário de bordo é A4 deitado; o eProtocolo e os scanners o devolvem
    "achatado" numa página retrato, de lado. Página com texto fica em pé e, sendo
    paisagem o conteúdo, em paisagem — nunca de cabeça para baixo. Página só de
    imagem: o OCR decide, se houver tesseract e `ocr`; sem ele, fica como está, a
    menos que `exigir_paisagem` (o importador, que depois mostra a conferência
    com ↺ ↻).

    `ocr=False` é para a saída (pacote final, "Baixar"): lá só a direção do texto
    vale — rápido, e o mesmo resultado sempre.

    PDF que não se lê volta intacto: endireitar é melhoria, não pode custar o
    documento.
    """
    from core.leitura.pdf import eh_pdf
    from core.leitura.pdf import normalizar_orientacao

    if not eh_pdf(dados):
        return dados, False
    try:
        if ocr:
            novo, _ = normalizar_orientacao(dados, exigir_paisagem=exigir_paisagem)
        else:
            novo = _em_pe_pelo_texto(dados)
    except Exception as exc:  # PDF torto: o diário entra como veio
        capture(exc, "prestacoes.diario.orientacao", level=logging.WARNING)
        return dados, False
    return novo, novo is not dados and novo != dados


def _em_pe_pelo_texto(dados: bytes) -> bytes:
    """Cada página com /Rotate = direção do texto; sem texto que decida, como está."""
    from core.leitura.pdf import ler_paginas
    from core.leitura.pdf import recortar
    from core.leitura.pdf import rotacao_para_ficar_em_pe

    paginas = ler_paginas(dados)
    finais = {}
    for pagina in paginas:
        rotacao = rotacao_para_ficar_em_pe(pagina)
        finais[pagina.indice] = pagina.rotacao if rotacao is None else rotacao
    if all(finais[p.indice] == p.rotacao for p in paginas):
        return dados
    return recortar(dados, [p.indice for p in paginas], finais)


def descrever_paginas(indices: list[int]) -> str:
    """"3-4", "7", "3-4, 9" — as folhas do processo (numeradas a partir de 1)."""
    numeros = sorted({int(i) + 1 for i in indices})
    if not numeros:
        return ""
    faixas = []
    inicio = anterior = numeros[0]
    for numero in numeros[1:]:
        if numero == anterior + 1:
            anterior = numero
            continue
        faixas.append((inicio, anterior))
        inicio = anterior = numero
    faixas.append((inicio, anterior))
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in faixas)
