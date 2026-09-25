from __future__ import annotations

from io import BytesIO

from django.urls import reverse

from documentos.services.exceptions import DocumentValidationError
from documentos.services.types import DocumentoFormato

from .diario_services import gerar_diario_bordo_pdf
from .models import ORDEM_DOCUMENTOS_PRESTACAO
from .models import DiarioBordo
from .models import PrestacaoDocumentoAnexo
from .models import RelatorioTecnico
from .services import _merge_pdf_parts
from .services import gerar_oficio_prestacao_documento
from .services import gerar_relatorio_tecnico_docx
from .services import gerar_relatorio_tecnico_pdf
from .services import pdf_do_anexo


#: Id do item no modal "Baixar documentos" → tipo do anexo, na ordem da prestação
#: (`ORDEM_DOCUMENTOS_PRESTACAO`): ofício, despacho, RT, diário, comprovante.
_ITEM_DO_TIPO = {
    PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO: "oficio",
    PrestacaoDocumentoAnexo.TIPO_DESPACHO: "despacho",
    PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO: "rt",
    PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO: "diario",
    PrestacaoDocumentoAnexo.TIPO_COMPROVANTE: "comprovante",
}
TIPOS = {_ITEM_DO_TIPO[tipo]: tipo for tipo in ORDEM_DOCUMENTOS_PRESTACAO}


def anexos_por_tipo(ps) -> dict[str, list]:
    """Todos os anexos que valem para este servidor, por tipo, na ordem do pacote.

    Compartilhados (ofício, despacho, diário: `servidor_prestacao` vazio) e os dele
    (RT, comprovantes). Lista, e não um anexo por tipo: dois despachos ou três
    comprovantes entram todos — antes o último ganhava e os outros sumiam do download.
    """
    compartilhados = list(ps.prestacao.documentos_anexos.filter(servidor_prestacao__isnull=True))
    individuais = list(ps.documentos_anexos.all())
    saida = {}
    for tipo in ORDEM_DOCUMENTOS_PRESTACAO:
        dele = [anexo for anexo in individuais if anexo.tipo == tipo]
        saida[tipo] = _ordenar(dele or [anexo for anexo in compartilhados if anexo.tipo == tipo], tipo)
    return saida


def _ordenar(anexos, tipo):
    """A ordem de `models.ordenacao_dos_anexos`, em memória (a lista já veio do prefetch)."""
    from datetime import date
    from datetime import datetime

    if tipo == PrestacaoDocumentoAnexo.TIPO_COMPROVANTE:
        chave = lambda a: (a.data_operacao is None, a.data_operacao or date.min, a.criado_em or datetime.min, a.pk)  # noqa: E731
    else:
        chave = lambda a: (a.criado_em or datetime.min, a.pk)  # noqa: E731
    return sorted(anexos, key=chave)


def _signed_url(ps, item_id, anexos):
    if not anexos:
        return ""
    return reverse("viagens_prestacoes:prestacao_download_assinado", args=[ps.pk, item_id, "pdf"])


def payload_downloads(ps):
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
    definicoes = {
        "oficio": ("Ofício", oficio.numero_formatado, oficio_urls),
        "despacho": ("Despacho", "Documento do ofício", {}),
        "rt": ("Relatório técnico", ps.servidor.nome, rt_urls),
        "diario": ("Diário de bordo", oficio.numero_formatado, diario_urls),
        "comprovante": ("Comprovante", ps.servidor.nome, {}),
    }
    itens = []
    for item_id, tipo in TIPOS.items():
        titulo, subtitulo, originais = definicoes[item_id]
        assinados = anexos.get(tipo) or []
        if len(assinados) > 1:
            titulo = f"{titulo} ({len(assinados)})"
        versoes = {
            "original": originais,
            "assinado": {"pdf": _signed_url(ps, item_id, assinados)} if assinados else {},
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


def anexos_do_item(ps, item_id) -> list:
    """Os anexos assinados de um item do modal, na ordem do pacote (vazio se não houver)."""
    tipo = TIPOS.get(item_id)
    return anexos_por_tipo(ps).get(tipo, []) if tipo else []


def anexo_do_item(ps, item_id):
    """O primeiro anexo do item, ou None — para saber se há versão assinada."""
    anexos = anexos_do_item(ps, item_id)
    return anexos[0] if anexos else None


def pdf_assinado(ps, item_id):
    """O PDF assinado do item: todos os anexos dele juntos, na ordem do pacote."""
    anexos = anexos_do_item(ps, item_id)
    if not anexos:
        raise DocumentValidationError("Documento assinado não encontrado.")
    partes = [(anexo.get_tipo_display(), pdf_do_anexo(anexo, anexo.get_tipo_display())) for anexo in anexos]
    return partes[0][1] if len(partes) == 1 else _merge_pdf_parts(partes)


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
    if "rt" in escolhidos:
        relatorio, _ = RelatorioTecnico.objects.get_or_create(prestacao=prestacao)
        gerador = gerar_relatorio_tecnico_pdf if formato == "pdf" else gerar_relatorio_tecnico_docx
        partes.append(("relatório técnico", gerador(relatorio, ps)))
    if "diario" in escolhidos:
        if formato != "pdf":
            raise DocumentValidationError("O diário de bordo não possui versão DOCX.")
        try:
            diario = prestacao.diario_bordo
        except DiarioBordo.DoesNotExist as exc:
            raise DocumentValidationError("Diário de bordo não encontrado.") from exc
        partes.append(("diário de bordo", gerar_diario_bordo_pdf(diario)))
    return partes


def na_ordem_da_prestacao(itens) -> list[str]:
    """Os ids do modal na ordem de `ORDEM_DOCUMENTOS_PRESTACAO`, sem repetir."""
    return [item for item in TIPOS if item in set(itens)]


def compilar_download(ps, *, origem, formato, escolhidos):
    escolhidos = na_ordem_da_prestacao(escolhidos)
    if origem == "assinado":
        if formato != "pdf":
            raise DocumentValidationError("Documentos assinados estão disponíveis em PDF.")
        partes = [(item_id, pdf_assinado(ps, item_id)) for item_id in escolhidos]
    else:
        partes = _originais(ps, formato, escolhidos)
    if not partes:
        raise DocumentValidationError("Nenhum documento está disponível nesta combinação.")
    return _merge_pdf_parts(partes) if formato == "pdf" else _fundir_docx([parte[1] for parte in partes])
