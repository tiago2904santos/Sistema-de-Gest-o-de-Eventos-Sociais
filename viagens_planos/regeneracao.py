"""Como refazer o PDF do plano de trabalho a partir do artefato."""

from documentos.services.types import DocumentoFormato, DocumentoTipo


def _refazer(artefato):
    plano = artefato.plano_trabalho
    if plano is None:
        return None
    from .services import gerar_plano_documento

    return gerar_plano_documento(plano, DocumentoFormato.PDF, usar_assinado=False).conteudo


def registrar_regeradores():
    from documentos.services.regeneracao import registrar

    registrar(DocumentoTipo.PLANO_TRABALHO, _refazer)
