from __future__ import annotations

from io import BytesIO

from django.urls import reverse

from documentos.services.exceptions import DocumentValidationError
from documentos.services.types import DocumentoFormato

from .diario_services import gerar_diario_bordo_pdf
from .models import DiarioBordo
from .models import PrestacaoDocumentoAnexo
from .models import RelatorioTecnico
from .services import _merge_pdf_parts
from .services import _pdf_bytes_from_file_field
from .services import gerar_oficio_prestacao_documento
from .services import gerar_relatorio_tecnico_docx
from .services import gerar_relatorio_tecnico_pdf


TIPOS = {
    "oficio": PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO,
    "despacho": PrestacaoDocumentoAnexo.TIPO_DESPACHO,
    "diario": PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO,
    "rt": PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO,
    "comprovante": PrestacaoDocumentoAnexo.TIPO_COMPROVANTE,
}


def anexos_por_tipo(ps):
    compartilhados = {
        item.tipo: item
        for item in ps.prestacao.documentos_anexos.filter(servidor_prestacao__isnull=True)
    }
    individuais = {item.tipo: item for item in ps.documentos_anexos.all()}
    return {**compartilhados, **individuais}


def _signed_url(ps, item_id, anexo):
    if not anexo:
        return ""
    return reverse("viagens_prestacoes:prestacao_download_assinado", args=[ps.pk, item_id, "pdf"])


def payload_downloads(ps):
    from .assinatura_services import assinatura_rt, assinatura_db
    eletronicos = {"rt": assinatura_rt(ps), "diario": assinatura_db(ps.prestacao)}
    prestacao = ps.prestacao
    oficio = prestacao.oficio
    anexos = anexos_por_tipo(ps)
    try:
        diario = prestacao.diario_bordo
    except DiarioBordo.DoesNotExist:
        diario = None
    oficio_urls = {
        formato: reverse("viagens_oficios:gerar", args=[oficio.pk, "oficio", formato])
        for formato in ("pdf", "docx")
    }
    rt_urls = {
        formato: reverse("viagens_prestacoes:rt_download_servidor_formato", args=[ps.pk, formato])
        for formato in ("pdf", "docx")
    }
    diario_urls = (
        {"pdf": reverse("viagens_prestacoes:diario_download_formato", args=[diario.pk, "pdf"])}
        if diario else {}
    )
    definicoes = [
        ("oficio", "Ofício", oficio.numero_formatado, oficio_urls),
        ("despacho", "Despacho", "Documento do ofício", {}),
        ("diario", "Diário de bordo", oficio.numero_formatado, diario_urls),
        ("rt", "Relatório técnico", ps.servidor.nome, rt_urls),
        ("comprovante", "Comprovante", ps.servidor.nome, {}),
    ]
    itens = []
    for item_id, titulo, subtitulo, originais in definicoes:
        assinado = anexos.get(TIPOS[item_id])
        eletronico = eletronicos.get(item_id)
        assinado = assinado or (eletronico if eletronico and eletronico.assinada and eletronico.arquivo_assinado else None)
        versoes = {
            "original": originais,
            "assinado": {"pdf": _signed_url(ps, item_id, assinado)} if assinado else {},
        }
        if any(versoes.values()):
            itens.append({"id": item_id, "titulo": titulo, "subtitulo": subtitulo, "versoes": versoes})
    return {
        "itens": itens,
        "compilado": reverse("viagens_prestacoes:prestacao_download_compilado", args=[ps.pk]),
        "origens": [
            {"value": "original", "label": "Original do sistema"},
            {"value": "assinado", "label": "Documento assinado"},
        ],
        "sempre_escolher": True,
        "compilado_aceita_itens": True,
    }


def anexo_do_item(ps, item_id):
    tipo = TIPOS.get(item_id)
    return anexos_por_tipo(ps).get(tipo) if tipo else None


def pdf_assinado(ps, item_id):
    anexo = anexo_do_item(ps, item_id)
    if not anexo:
        from .assinatura_services import assinatura_rt, assinatura_db, _bytes_assinado
        doc = assinatura_rt(ps) if item_id == "rt" else assinatura_db(ps.prestacao) if item_id == "diario" else None
        conteudo = _bytes_assinado(doc)
        if conteudo is not None:
            return conteudo
        raise DocumentValidationError("Documento assinado não encontrado.")
    return _pdf_bytes_from_file_field(anexo.arquivo, anexo.get_tipo_display())


def _fundir_docx(conteudos):
    from docx import Document
    from docxcompose.composer import Composer

    base = Document(BytesIO(conteudos[0]))
    composer = Composer(base)
    for conteudo in conteudos[1:]:
        base.add_page_break()
        composer.append(Document(BytesIO(conteudo)))
    output = BytesIO()
    composer.save(output)
    return output.getvalue()


def _originais(ps, formato, escolhidos):
    prestacao = ps.prestacao
    partes = []
    if "oficio" in escolhidos:
        partes.append(("ofício", gerar_oficio_prestacao_documento(prestacao, DocumentoFormato(formato))))
    if "diario" in escolhidos:
        if formato != "pdf":
            raise DocumentValidationError("O diário de bordo não possui versão DOCX.")
        try:
            diario = prestacao.diario_bordo
        except DiarioBordo.DoesNotExist as exc:
            raise DocumentValidationError("Diário de bordo não encontrado.") from exc
        partes.append(("diário de bordo", gerar_diario_bordo_pdf(diario)))
    if "rt" in escolhidos:
        relatorio, _ = RelatorioTecnico.objects.get_or_create(prestacao=prestacao)
        gerador = gerar_relatorio_tecnico_pdf if formato == "pdf" else gerar_relatorio_tecnico_docx
        partes.append(("relatório técnico", gerador(relatorio, ps)))
    return partes


def compilar_download(ps, *, origem, formato, escolhidos):
    if origem == "assinado":
        if formato != "pdf":
            raise DocumentValidationError("Documentos assinados estão disponíveis em PDF.")
        partes = [(item_id, pdf_assinado(ps, item_id)) for item_id in escolhidos]
    else:
        partes = _originais(ps, formato, escolhidos)
    if not partes:
        raise DocumentValidationError("Nenhum documento está disponível nesta combinação.")
    return _merge_pdf_parts(partes) if formato == "pdf" else _fundir_docx([parte[1] for parte in partes])
