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


# ---- "Assinado, mas os dados mudaram" (m109) ------------------------------
#
# O PDF assinado vale no lugar do gerado, mas nada o liga aos dados de hoje:
# se o cadastro do servidor, o roteiro ou a configuração mudam depois da
# assinatura, o arquivo entregue já não corresponde ao sistema. O artefato
# guarda o payload com que o PDF nasceu (`payload_snapshot`); comparar esse
# snapshot com o payload de agora diz se o assinado ficou para trás, e o quê.

ROTULOS_DAS_PARTES = {
    "oficio": "Ofício", "institucional": "Configuração do setor", "justificativa": "Justificativa",
    "documento": "Textos do documento", "ordem_servico": "Ordem de serviço", "plano": "Plano de trabalho",
    "participante": "Servidor", "viagem": "Viagem", "transporte": "Transporte", "textos": "Textos do termo",
    "header": "Cabeçalho do diário", "trechos": "Trechos do diário",
}


def artefato_assinado(artefatos):
    """O artefato cuja versão assinada vale (a viva mais recente; na falta,
    o do modelo antigo com `arquivo_assinado`), ou None."""
    from documentos.models import DocumentoAssinaturaVersao

    versao = (DocumentoAssinaturaVersao.objects
              .filter(artefato__in=artefatos, revogada_em__isnull=True)
              .select_related("artefato").order_by("-criado_em").first())
    if versao is not None:
        return versao.artefato
    return artefatos.exclude(arquivo_assinado="").order_by("-criado_em").first()


def mudancas_desde_a_assinatura(artefato, payload_atual) -> list[str]:
    """O que mudou nos dados desde que o PDF assinado foi gerado, uma linha
    por parte ("Ofício: motivo, servidores"). Vazia, o assinado ainda bate.

    Artefato sem snapshot (gerado antes de o snapshot existir) ou documento
    sem payload comparável não têm como ser conferidos: também vazia.
    """
    from documentos.services.persistence import _payload_snapshot_json_seguro

    antes = (artefato.payload_snapshot or {}) if artefato is not None else {}
    if not antes or payload_atual is None:
        return []
    agora = _payload_snapshot_json_seguro(payload_atual)
    mudancas = []
    for parte in sorted(set(antes) | set(agora)):
        a, b = antes.get(parte), agora.get(parte)
        if a == b:
            continue
        rotulo = ROTULOS_DAS_PARTES.get(parte, parte)
        if isinstance(a, dict) and isinstance(b, dict):
            campos = sorted(chave for chave in set(a) | set(b) if a.get(chave) != b.get(chave))
            mudancas.append(f"{rotulo}: {', '.join(campos)}")
        else:
            mudancas.append(rotulo)
    return mudancas
