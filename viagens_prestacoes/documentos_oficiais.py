"""PDFs gerados do RT e do diário de bordo, usados no compilado da prestação."""

from .models import DiarioBordo, RelatorioTecnico


def pdf_rt_gerado(servidor_prestacao) -> bytes:
    from .services import gerar_relatorio_tecnico_pdf

    relatorio, _ = RelatorioTecnico.objects.get_or_create(prestacao=servidor_prestacao.prestacao)
    return gerar_relatorio_tecnico_pdf(relatorio, servidor_prestacao)


def pdf_db_gerado(prestacao) -> bytes:
    from .diario_services import gerar_diario_bordo_pdf

    diario, _ = DiarioBordo.objects.get_or_create(prestacao=prestacao)
    return gerar_diario_bordo_pdf(diario)
