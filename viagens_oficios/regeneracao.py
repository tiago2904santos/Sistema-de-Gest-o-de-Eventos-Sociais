"""Como refazer o PDF do ofício e da justificativa a partir do artefato."""

from documentos.services.types import DocumentoFormato, DocumentoTipo


def _refazer(artefato, tipo):
    oficio = artefato.oficio
    if oficio is None:
        return None
    from .document_generation import gerar_documento

    # `usar_assinado=False`: o que se refaz é o documento gerado, nunca o PDF
    # assinado que alguém anexou por cima.
    return gerar_documento(oficio, DocumentoFormato.PDF, tipo, usar_assinado=False).conteudo


def registrar_regeradores():
    from documentos.services.regeneracao import registrar

    registrar(DocumentoTipo.OFICIO, lambda a: _refazer(a, DocumentoTipo.OFICIO))
    registrar(DocumentoTipo.JUSTIFICATIVA, lambda a: _refazer(a, DocumentoTipo.JUSTIFICATIVA))
