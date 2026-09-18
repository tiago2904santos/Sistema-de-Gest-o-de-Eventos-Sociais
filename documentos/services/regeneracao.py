"""Refazer, no download, um PDF que nasceu do caminho antigo.

Um artefato gerado antes da migração para HTML + WeasyPrint saiu da cadeia
Word/LibreOffice: ele não tem a letra, as colunas nem os campos do documento
de hoje. No download, em vez de entregar esse arquivo, o sistema o refaz.

Refazer exige voltar ao registro de origem: o artefato guarda só o `payload`
em `payload_snapshot`, e não o contexto que alimenta os templates. Por isso
cada app de viagens registra aqui, no `ready()` do seu AppConfig, como refazer
o tipo que ela gera — assim `documentos` continua sem importar as apps que
dependem dela.

Um tipo sem regerador registrado (ou cujo registro de origem sumiu) continua
sendo servido do arquivo arquivado: entregar o documento antigo é melhor que
negar o download.
"""

from __future__ import annotations

import logging
from typing import Callable

from documentos.services.types import DocumentoFormato

logger = logging.getLogger(__name__)

# Como a façade marca o artefato que nasceu do HTML.
MOTOR_ATUAL = "html_weasyprint"

_REGERADORES: dict[str, Callable[[object], bytes | None]] = {}


def registrar(tipo, funcao: Callable[[object], bytes | None]) -> None:
    """Liga um tipo de documento à função que refaz o PDF dele.

    A função recebe o artefato e devolve os bytes do PDF, ou `None` quando o
    registro de origem não existe mais.
    """
    _REGERADORES[str(getattr(tipo, "value", tipo))] = funcao


def precisa_regerar(artefato, *, assinado: bool) -> bool:
    """Só PDF, só tipo que hoje nasce do HTML, só o que veio do motor antigo.

    O arquivo assinado nunca é refeito: ele é o que a pessoa anexou depois da
    assinatura, não algo que o sistema saiba reproduzir.
    """
    if assinado or artefato.formato != DocumentoFormato.PDF.value:
        return False
    if artefato.engine == MOTOR_ATUAL:
        return False
    if artefato.tipo not in _REGERADORES:
        return False
    from documentos.services.pdf_renderer import tipo_e_html_nativo

    return tipo_e_html_nativo(artefato.tipo)


def regerar(artefato) -> bytes | None:
    """Bytes do PDF refeito, ou `None` se não der — e aí o download segue com
    o arquivo arquivado, como antes."""
    funcao = _REGERADORES.get(artefato.tipo)
    if funcao is None:
        return None
    try:
        return funcao(artefato)
    except Exception:
        logger.warning(
            "Não foi possível refazer o %s %s; servindo o arquivo arquivado.",
            artefato.tipo, artefato.pk, exc_info=True,
        )
        return None
