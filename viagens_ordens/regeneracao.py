"""Como refazer o PDF da ordem de serviço a partir do artefato."""

from documentos.services.types import DocumentoFormato, DocumentoTipo


def _refazer(artefato):
    ordem = artefato.ordem_servico
    if ordem is None:
        return None
    from .services import gerar_ordem_servico

    return gerar_ordem_servico(ordem, DocumentoFormato.PDF, usar_assinado=False).conteudo


def registrar_regeradores():
    from documentos.services.regeneracao import registrar

    registrar(DocumentoTipo.ORDEM_SERVICO, _refazer)
