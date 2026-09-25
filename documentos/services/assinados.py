"""A versão assinada vale no lugar do PDF gerado.

Depois que alguém anexa o PDF assinado de um documento, todo pedido do PDF
desse mesmo documento — visualizar, baixar, o PDF único, o ZIP — entrega o
arquivo anexado, e não uma nova geração. Vale até a versão ser removida.

"Mesmo documento" é o mesmo tipo, os mesmos vínculos (ofício, termo,
prestação, servidor) e a mesma referência de geração, que entra no nome do
arquivo (`<tipo>_<referência>_<data>.pdf`). A referência separa, por exemplo,
o termo vazio do termo da viatura, que têm os mesmos vínculos.
"""

from __future__ import annotations

import hashlib
import logging

from documentos.services.filenames import build_document_filename, slugify_filename_part

logger = logging.getLogger(__name__)


def _candidatos(tipo, *, oficio_id, termo_id, prestacao_id, servidor_id, reference,
                ordem_servico_id=None, plano_trabalho_id=None):
    from documentos.models import DocumentoArtefato

    filtro = {
        "tipo": tipo.value, "formato": "pdf",
        "oficio_id": oficio_id, "termo_id": termo_id,
        "prestacao_id": prestacao_id, "servidor_id": servidor_id,
        "ordem_servico_id": ordem_servico_id, "plano_trabalho_id": plano_trabalho_id,
    }
    consulta = DocumentoArtefato.objects.filter(**filtro)
    if reference:
        consulta = consulta.filter(nome_exibicao__contains=f"_{slugify_filename_part(reference)}_")
    return consulta


def artefatos_do_documento(tipo, *, reference=None, oficio_id=None, termo_id=None, prestacao_id=None, servidor_id=None,
                           ordem_servico_id=None, plano_trabalho_id=None):
    """Os PDFs gerados de um documento: mesmo tipo, mesmos vínculos e mesma referência.

    É o recorte com que `versao_assinada_vigente` procura a versão assinada; quem
    anexa o assinado de fora da tela do artefato (o importador de processo) usa
    este mesmo recorte para escolher onde anexar, e assim a versão anexada é a
    que a geração devolve depois.
    """
    return _candidatos(tipo, oficio_id=oficio_id, termo_id=termo_id, prestacao_id=prestacao_id,
                       servidor_id=servidor_id, reference=reference,
                       ordem_servico_id=ordem_servico_id, plano_trabalho_id=plano_trabalho_id)


def versao_assinada_vigente(tipo, *, oficio_id=None, termo_id=None, prestacao_id=None, servidor_id=None, reference=None,
                            ordem_servico_id=None, plano_trabalho_id=None):
    """O arquivo assinado que vale para este documento, ou None.

    A versão viva mais recente entre todos os PDFs do documento; na falta
    dela, o `arquivo_assinado` do modelo antigo, do artefato mais recente.
    """
    from documentos.models import DocumentoAssinaturaVersao

    if not (oficio_id or termo_id or prestacao_id or ordem_servico_id or plano_trabalho_id):
        return None
    artefatos = _candidatos(tipo, oficio_id=oficio_id, termo_id=termo_id, prestacao_id=prestacao_id,
                            servidor_id=servidor_id, reference=reference,
                            ordem_servico_id=ordem_servico_id, plano_trabalho_id=plano_trabalho_id)
    versao = (DocumentoAssinaturaVersao.objects
              .filter(artefato__in=artefatos, revogada_em__isnull=True)
              .order_by("-criado_em").first())
    if versao is not None:
        return versao.arquivo
    legado = artefatos.exclude(arquivo_assinado="").order_by("-criado_em").first()
    return legado.arquivo_assinado if legado is not None else None


def documento_assinado(tipo, formato, *, reference=None, **vinculos):
    """O `DocumentoGerado` com o conteúdo do assinado, ou None para gerar."""
    from documentos.services.facade import DocumentoGerado
    from documentos.services.responses import get_content_type_for_format

    arquivo = versao_assinada_vigente(tipo, reference=reference, **vinculos)
    if arquivo is None:
        return None
    try:
        with arquivo.open("rb") as handle:
            conteudo = handle.read()
    except (FileNotFoundError, OSError, ValueError):
        logger.warning("Versão assinada sem arquivo no storage (%s); gerando o PDF.", getattr(arquivo, "name", "?"))
        return None
    return DocumentoGerado(
        tipo=tipo,
        formato=formato,
        nome_arquivo=build_document_filename(tipo, formato, reference=f"{reference}-assinado" if reference else "assinado"),
        content_type=get_content_type_for_format(formato),
        conteudo=conteudo,
        hash_sha256=hashlib.sha256(conteudo).hexdigest(),
        pdf_engine_used="assinado",
        cache_hit=True,
    )
