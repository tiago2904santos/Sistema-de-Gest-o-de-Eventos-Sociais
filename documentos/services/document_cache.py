"""
Chave de cache e leitura de artefatos documentais já persistidos (PDF/DOCX).

A chave incorpora tipo, formato, referência, inputs (payload + docxtpl), templates
e cadeia de motores PDF resolvida — não basta `updated_at` do Ofício.
"""

from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from django.conf import settings
from django.template import TemplateDoesNotExist
from django.template.loader import get_template

from documentos.models import DocumentoArtefato
from documentos.services.resources_paths import resolve_resource_docx
from documentos.services.templates import default_template_registry
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo

logger = logging.getLogger(__name__)


def _json_default(o: object) -> str:
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (bytes, memoryview)):
        return bytes(o).hex()[:128]
    return str(o)


def canonical_json_blob(data: Mapping[str, Any] | None) -> str:
    if not data:
        return "{}"
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_json_default)


def _file_fp(path: Path) -> str:
    try:
        st = path.stat()
        return f"{path.resolve()}:{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return f"{path}:missing"


def _caminho_do_html(nome: str) -> Path:
    """Caminho em disco do modelo HTML registrado.

    O nome vem relativo ao motor de templates (`documentos/pdf/oficio.html`) e
    não ao `BASE_DIR`: o arquivo mora em `templates/`. Concatenar com o
    `BASE_DIR` devolvia sempre um caminho inexistente, e a impressão digital
    ficava constante — editar o modelo do PDF não invalidava o artefato já em
    cache. Resolver pelo carregador de templates é o que fecha esse buraco.
    """
    try:
        template = get_template(nome)
    except TemplateDoesNotExist:
        template = None
    origem = getattr(getattr(template, "origin", None), "name", "")
    if origem:
        return Path(origem)
    return Path(settings.BASE_DIR) / "templates" / nome


def build_template_cache_signature(
    *,
    tipo: DocumentoTipo,
    formato: DocumentoFormato,
    docx_template_path: str | None = None,
    template_registry=default_template_registry,
) -> str:
    """DOCX + (para PDF) HTML e CSS registados — invalida cache quando o modelo muda."""
    if tipo == DocumentoTipo.DIARIO_BORDO:
        return _file_fp(Path(settings.BASE_DIR) / "documentos/resources/diario_bordo.xlsx")
    parts: list[str] = []
    docx_def = template_registry.get(tipo, DocumentoFormato.DOCX)
    parts.append(
        _file_fp(
            resolve_resource_docx(
                docx_template_path or docx_def.template_path,
            )
        )
    )
    if formato == DocumentoFormato.PDF:
        from documentos.services.pdf_renderer import caminhos_dos_templates, tipo_e_html_nativo

        if tipo_e_html_nativo(tipo):
            # Caminho HTML → PDF: o template do tipo, a folha institucional e
            # os dois CSS; mudou qualquer um, o artefato em cache cai.
            parts.extend(_file_fp(p) for p in caminhos_dos_templates(tipo))
        else:
            html_def = template_registry.get(tipo, DocumentoFormato.PDF)
            base = Path(settings.BASE_DIR)
            parts.append(_file_fp(_caminho_do_html(html_def.template_path)))
            for rel in html_def.stylesheet_paths:
                parts.append(_file_fp(base / rel))
    return "|".join(parts)


def build_document_cache_key(
    *,
    tipo: DocumentoTipo,
    formato: DocumentoFormato,
    reference: str | None,
    payload: Mapping[str, Any],
    docxtpl_context: Mapping[str, Any] | None,
    attempt_chain: tuple[str, ...] | None,
    template_signature: str,
) -> str:
    """
    Gera chave estável (hex SHA-256 truncada a 128 chars) para bater com `DocumentoArtefato.cache_key`.
    """
    gen_ver = str(getattr(settings, "DOCUMENTOS_GENERATOR_VERSION", "1") or "1")
    chain = ",".join(attempt_chain or ()) if attempt_chain is not None else ""

    parts = "|".join(
        [
            gen_ver,
            tipo.value,
            formato.value,
            (reference or "").strip(),
            canonical_json_blob(dict(payload)),
            canonical_json_blob(dict(docxtpl_context or {})),
            template_signature,
            chain,
        ],
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:128]


def get_cached_document_artifact(
    *,
    roteiro_id: int | None = None,
    oficio_id: int | None = None,
    termo_id: int | None = None,
    prestacao_id: int | None = None,
    criado_por_id: int | None = None,
    servidor_id: int | None = None,
    tipo: DocumentoTipo,
    formato: DocumentoFormato,
    cache_key: str,
) -> DocumentoArtefato | None:
    # Sem tenancy: as FKs opcionais e o criador definem o contexto do cache.
    if not cache_key or not getattr(settings, "DOCUMENTOS_ARTIFACT_CACHE", True):
        return None
    try:
        filters: dict[str, Any] = {
            "tipo": tipo.value,
            "formato": formato.value,
            "cache_key": cache_key,
        }
        filters.update(
            roteiro_id=roteiro_id, oficio_id=oficio_id, termo_id=termo_id, prestacao_id=prestacao_id, servidor_id=servidor_id, criado_por_id=criado_por_id,
        )
        art = DocumentoArtefato.objects.filter(**filters).order_by("-criado_em").first()
    except Exception:
        logger.exception("Falha ao consultar cache documental.")
        return None
    if art is None or not art.arquivo:
        return None
    try:
        name = art.arquivo.name
        if not name:
            return None
        if not art.arquivo.storage.exists(name):
            return None
    except Exception as exc:
        logger.exception("Falha ao verificar arquivo do cache documental")
        return None
    return art


def read_artifact_file_bytes(artefato: DocumentoArtefato) -> bytes:
    with artefato.arquivo.open("rb") as fh:
        return fh.read()


def documento_gerado_from_artifact(
    artefato: DocumentoArtefato,
    *,
    tipo: DocumentoTipo,
    formato: DocumentoFormato,
    reference: str | None,
):
    """Reconstrói o valor de domínio sem executar novamente o renderizador."""
    from documentos.services.facade import DocumentoGerado
    from documentos.services.filenames import build_document_filename
    from documentos.services.responses import get_content_type_for_format

    return DocumentoGerado(
        tipo=tipo,
        formato=formato,
        nome_arquivo=artefato.nome_exibicao or build_document_filename(tipo, formato, reference=reference),
        content_type=get_content_type_for_format(formato),
        conteudo=read_artifact_file_bytes(artefato),
        hash_sha256=artefato.hash_sha256,
        pdf_engine_used=(artefato.engine or None) if formato == DocumentoFormato.PDF else None,
        artefato_id=artefato.pk,
        cache_hit=True,
    )
