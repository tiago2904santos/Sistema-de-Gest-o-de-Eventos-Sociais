from __future__ import annotations

import datetime
import enum
import hashlib
import json
import logging
import uuid
from decimal import Decimal
from typing import Any, Mapping

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Model
from django.db.models.query import QuerySet
from django.utils import timezone

from documentos.models import DocumentoArtefato
from documentos.models import DocumentoAssinaturaVersao
from documentos.services.exceptions import ArquivoAssinadoInvalido
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from documentos.services.facade import DocumentoGerado
from documentos.services.timing import measure_step

logger = logging.getLogger(__name__)

_MAX_SNAPSHOT_DEPTH = 48
_ARQUIVO_ASSINADO_MAX_BYTES = 15 * 1024 * 1024


def _sanear_objeto_para_json(val: Any, *, _depth: int = 0) -> Any:
    """
    Converte valores arbitrários do contexto/payload documental em tipos aceites por JSONField
    (inclui instâncias de modelos Django aninhados, QuerySets, datas, etc.).
    """
    if _depth > _MAX_SNAPSHOT_DEPTH:
        return "<profundidade-maxima>"
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, enum.Enum):
        return val.value
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    if isinstance(val, datetime.time):
        return val.isoformat()
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    if isinstance(val, bytearray):
        return bytes(val).decode("utf-8", errors="replace")
    if isinstance(val, memoryview):
        return val.tobytes().decode("utf-8", errors="replace")
    if isinstance(val, Model):
        return str(val)
    if isinstance(val, QuerySet):
        return [_sanear_objeto_para_json(x, _depth=_depth + 1) for x in val[:2000]]
    if isinstance(val, dict):
        return {str(k): _sanear_objeto_para_json(v, _depth=_depth + 1) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanear_objeto_para_json(x, _depth=_depth + 1) for x in val]
    if isinstance(val, set):
        return [_sanear_objeto_para_json(x, _depth=_depth + 1) for x in sorted(val, key=lambda x: str(x))]
    return str(val)


def _payload_snapshot_json_seguro(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """Garante estrutura compatível com JSONField e com o adaptador JSON do psycopg."""
    raw = _sanear_objeto_para_json(dict(snapshot or {}))
    return json.loads(json.dumps(raw, default=str))


def persist_geracao(
    doc: DocumentoGerado,
    *,
    roteiro_id: int | None = None,
    oficio_id: int | None = None,
    termo_id: int | None = None,
    prestacao_id: int | None = None,
    ordem_servico_id: int | None = None,
    plano_trabalho_id: int | None = None,
    servidor_id: int | None = None,
    criado_por_id: int | None = None,
    nome_exibicao: str = "",
    payload_snapshot: Mapping[str, Any] | None = None,
    cache_key: str = "",
    engine: str = "",
    generator_version: str = "",
) -> DocumentoArtefato | None:
    if not getattr(settings, "DOCUMENTOS_PERSIST_ARTEFATOS", True):
        return None
    nome = doc.nome_arquivo
    arquivo = ContentFile(doc.conteudo, name=nome)
    payload_snapshot = _payload_snapshot_json_seguro(payload_snapshot)
    gen_ver = generator_version or str(getattr(settings, "DOCUMENTOS_GENERATOR_VERSION", "1") or "1")
    with measure_step(
        "persist_geracao",
        {
            "tipo": doc.tipo.value,
            "formato": doc.formato.value,
            "roteiro_id": roteiro_id,
            "servidor_id": servidor_id,
            "criado_por_id": criado_por_id,
        },
    ):
        artefato = DocumentoArtefato(
            tipo=doc.tipo.value,
            formato=doc.formato.value,
            roteiro_id=roteiro_id, oficio_id=oficio_id, termo_id=termo_id, prestacao_id=prestacao_id,
            ordem_servico_id=ordem_servico_id, plano_trabalho_id=plano_trabalho_id,
            servidor_id=servidor_id,
            criado_por_id=criado_por_id,
            nome_exibicao=nome_exibicao or nome,
            payload_snapshot=payload_snapshot,
            hash_sha256=doc.hash_sha256,
            arquivo=arquivo,
            cache_key=cache_key or "",
            engine=engine or doc.pdf_engine_used or "docxtpl",
            generator_version=gen_ver,
        )
        try:
            artefato.save()
        except Exception:
            if artefato.arquivo and artefato.arquivo._committed:
                artefato.arquivo.storage.delete(artefato.arquivo.name)
            raise
        # Uma geração chamada dentro da operação da prestação acompanha seu rollback.
        from viagens_prestacoes.arquivos import registrar_arquivo_criado
        registrar_arquivo_criado(artefato.arquivo.storage, artefato.arquivo.name)
        return artefato


def _validar_upload_assinado(upload: UploadedFile) -> None:
    nome = (upload.name or "").lower()
    if not nome.endswith(".pdf"):
        raise ArquivoAssinadoInvalido("Envie um arquivo PDF.")
    if upload.size > _ARQUIVO_ASSINADO_MAX_BYTES:
        raise ArquivoAssinadoInvalido("Arquivo maior que 15MB.")
    inicio = upload.read(5)
    upload.seek(0)
    if inicio != b"%PDF-":
        raise ArquivoAssinadoInvalido("O arquivo não parece ser um PDF válido.")


def anexar_arquivo_assinado(artefato: DocumentoArtefato, upload: UploadedFile) -> DocumentoArtefato:
    """Anexa manualmente a versão assinada (ex.: escaneada) de um artefato gerado.

    A partir daqui ela passa a ser a versão "oficial": preferida na exibição/
    download .
    """
    _validar_upload_assinado(upload)
    raw = upload.read()
    request = None
    try:
        from core.middleware import obter_requisicao_atual

        request = obter_requisicao_atual()
    except Exception as exc:
        logger.exception("Falha ao resolver ator da assinatura")
    actor = getattr(request, "user", None)
    if not getattr(actor, "is_authenticated", False):
        actor = None
    versao = DocumentoAssinaturaVersao(
        artefato=artefato,
        hash_sha256=hashlib.sha256(raw).hexdigest(),
        nome_original=upload.name or "",
        criado_por=actor,
    )
    versao.arquivo.save(
        f"assinado_{artefato.pk}_{versao.pk}.pdf",
        ContentFile(raw),
        save=False,
    )
    versao.save()
    # Compatibilidade de leitura para integrações antigas. O arquivo anterior
    # não é apagado e permanece preservado na respectiva versão.
    artefato.arquivo_assinado = versao.arquivo.name
    artefato.assinado_em = timezone.now()
    artefato.assinado_nome_original = upload.name or ""
    artefato.save(update_fields=["arquivo_assinado", "assinado_em", "assinado_nome_original"])
    return artefato


def remover_arquivo_assinado(artefato: DocumentoArtefato) -> DocumentoArtefato:
    """Revoga a versão vigente sem apagar o arquivo probatório."""
    versao = artefato.versoes_assinadas.filter(
        revogada_em__isnull=True,
    ).order_by("-criado_em").first()
    if versao is not None:
        request = None
        try:
            from core.middleware import obter_requisicao_atual

            request = obter_requisicao_atual()
        except Exception as exc:
            logger.exception("Falha ao resolver ator da revogação")
        actor = getattr(request, "user", None)
        versao.revogada_em = timezone.now()
        versao.revogada_por = actor if getattr(actor, "is_authenticated", False) else None
        versao.save(update_fields=["revogada_em", "revogada_por"])
    artefato.arquivo_assinado = ""
    artefato.assinado_em = None
    artefato.assinado_nome_original = ""
    artefato.save(update_fields=["arquivo_assinado", "assinado_em", "assinado_nome_original"])
    return artefato
