"""Como refazer o PDF do relatório técnico e do diário de bordo."""

from documentos.services.types import DocumentoFormato, DocumentoTipo


def _refazer_relatorio(artefato):
    prestacao = artefato.prestacao
    if prestacao is None or artefato.servidor_id is None:
        return None
    from .models import PrestacaoServidor, RelatorioTecnico

    relatorio = RelatorioTecnico.objects.filter(prestacao=prestacao).first()
    # O relatório é um por prestação, mas sai um documento por servidor.
    servidor_prestacao = PrestacaoServidor.objects.filter(
        prestacao=prestacao, servidor_id=artefato.servidor_id
    ).first()
    if relatorio is None or servidor_prestacao is None:
        return None
    from .services import gerar_relatorio_tecnico_documento

    return gerar_relatorio_tecnico_documento(relatorio, servidor_prestacao, DocumentoFormato.PDF).conteudo


def _refazer_diario(artefato):
    prestacao = artefato.prestacao
    if prestacao is None:
        return None
    from .models import DiarioBordo

    diario = DiarioBordo.objects.filter(prestacao=prestacao).first()
    if diario is None:
        return None
    from .diario_services import gerar_diario_bordo_documento

    return gerar_diario_bordo_documento(diario, DocumentoFormato.PDF).conteudo


def registrar_regeradores():
    from documentos.services.regeneracao import registrar

    registrar(DocumentoTipo.RELATORIO_TECNICO, _refazer_relatorio)
    registrar(DocumentoTipo.DIARIO_BORDO, _refazer_diario)
