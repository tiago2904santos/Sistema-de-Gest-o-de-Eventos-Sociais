from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, replace
from uuid import UUID
from typing import Mapping

from django.conf import settings

from documentos.services.adapters.docxtpl_render import render_docx_bytes
from documentos.services.adapters.libreoffice_pdf import convert_docx_to_pdf_libreoffice
from documentos.services.exceptions import DocumentValidationError
from documentos.services.filenames import build_document_filename
from documentos.services.libreoffice_resolve import resolve_libreoffice_binary
from documentos.services.pdf_engine import build_pdf_unavailable_message
from documentos.services.pdf_engine import resolve_pdf_engine
from documentos.services.registry import default_document_registry
from documentos.services.resources_paths import resolve_resource_docx
from documentos.services.responses import get_content_type_for_format
from documentos.services.templates import DocumentTemplateDefinition
from documentos.services.templates import canonical_required_keys
from documentos.services.templates import default_template_registry
from documentos.services.timing import measure_step
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo
from documentos.services.validators import DocumentValidatorRegistry
from documentos.services.validators import ensure_required_fields

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentoGerado:
    tipo: DocumentoTipo
    formato: DocumentoFormato
    nome_arquivo: str
    content_type: str
    conteudo: bytes
    hash_sha256: str
    pdf_engine_used: str | None = None
    artefato_id: UUID | None = None
    cache_hit: bool = False


def _versao_editada(payload):
    """A versão editada inteira que veio no payload (`documento`), ou None."""
    documental = payload.get("documento") if hasattr(payload, "get") else None
    editada = documental.get("versao_editada") if isinstance(documental, dict) else None
    return editada if isinstance(editada, dict) and editada.get("regioes") else None


class DocumentoFacade:
    def __init__(
        self,
        *,
        template_registry=default_template_registry,
        document_registry=default_document_registry,
        validator_registry: DocumentValidatorRegistry | None = None,
    ):
        self._templates = template_registry
        self._document_registry = document_registry
        self._validators = validator_registry or DocumentValidatorRegistry()

    def gerar(
        self,
        *,
        tipo: DocumentoTipo,
        formato: DocumentoFormato,
        payload: Mapping[str, object],
        reference: str | None = None,
        docxtpl_context: Mapping[str, object] | None = None,
        docx_template_path: str | None = None,
        servidor_id: int | None = None,
        roteiro_id: int | None = None,
        oficio_id: int | None = None,
        termo_id: int | None = None,
    prestacao_id: int | None = None,
        ordem_servico_id: int | None = None,
        plano_trabalho_id: int | None = None,
        criado_por=None,
        persistir: bool = True,
        usar_assinado: bool = True,
    ) -> DocumentoGerado:
        if not self._document_registry.has(tipo):
            from documentos.services.exceptions import UnsupportedDocumentType

            raise UnsupportedDocumentType(f"Tipo documental não suportado: {tipo.value}")
        type_def = self._document_registry.get(tipo)
        if not type_def.supports_format(formato):
            from documentos.services.exceptions import UnsupportedDocumentFormat

            raise UnsupportedDocumentFormat(
                f"Formato {formato.value} não permitido para {tipo.value}",
            )
        template_def = self._templates.get(tipo, formato)
        self._validate_payload(tipo, payload)
        artifact_cache_key = ""
        actor = criado_por
        if actor is None:
            from core.middleware import obter_requisicao_atual

            actor = getattr(obter_requisicao_atual(), "user", None)
        actor_id = actor.pk if getattr(actor, "is_authenticated", False) else None
        should_persist = persistir and getattr(settings, "DOCUMENTOS_PERSIST_ARTEFATOS", True)
        if should_persist and usar_assinado and formato == DocumentoFormato.PDF:
            # Documento com PDF assinado anexado: vale o anexado, não uma nova geração.
            from documentos.services.assinados import documento_assinado

            assinado = documento_assinado(
                tipo, formato, reference=reference, oficio_id=oficio_id, termo_id=termo_id,
                prestacao_id=prestacao_id, servidor_id=servidor_id,
                ordem_servico_id=ordem_servico_id, plano_trabalho_id=plano_trabalho_id,
            )
            if assinado is not None:
                return assinado
        if should_persist:
            from documentos.services.document_cache import (
                build_document_cache_key, build_template_cache_signature,
                documento_gerado_from_artifact, get_cached_document_artifact,
            )

            chain = None
            if formato == DocumentoFormato.PDF:
                from documentos.services.pdf_renderer import tipo_e_html_nativo

                if tipo_e_html_nativo(tipo):
                    # Caminho HTML → PDF: a cadeia entra na chave para nenhum
                    # artefato do caminho antigo (Word/LibreOffice) ser
                    # servido no lugar do novo.
                    chain = ("html_weasyprint",)
                else:
                    chain = resolve_pdf_engine(
                        explicit_setting=getattr(settings, "DOCUMENTOS_DEFAULT_PDF_ENGINE", "auto"),
                        prefer_docx_pipeline=docxtpl_context is not None,
                    ).attempt_chain
            artifact_cache_key = build_document_cache_key(
                tipo=tipo, formato=formato, reference=reference, payload=payload,
                docxtpl_context=docxtpl_context, attempt_chain=chain,
                template_signature=build_template_cache_signature(
                    tipo=tipo, formato=formato, docx_template_path=docx_template_path,
                    template_registry=self._templates,
                ),
            )
            cached = get_cached_document_artifact(
                tipo=tipo, formato=formato, cache_key=artifact_cache_key,
                servidor_id=servidor_id, roteiro_id=roteiro_id, oficio_id=oficio_id, termo_id=termo_id, prestacao_id=prestacao_id,
                ordem_servico_id=ordem_servico_id, plano_trabalho_id=plano_trabalho_id, criado_por_id=actor_id,
            )
            if cached is not None:
                return documento_gerado_from_artifact(
                    cached, tipo=tipo, formato=formato, reference=reference,
                )
        docx_ctx = docxtpl_context if docxtpl_context is not None else payload
        ref = (reference or "").strip()
        pdf_engine_used: str | None = None
        with measure_step(
            "facade_gerar",
            {"tipo": tipo.value, "formato": formato.value, "reference": ref or "—"},
        ):
            editada = _versao_editada(payload)
            if editada is not None and formato == DocumentoFormato.DOCX:
                # Documento editado à mão (m057): o DOCX sai do HTML da versão
                # editada, não do modelo .docx.
                from documentos.services.html_docx import regioes_para_docx

                conteudo = regioes_para_docx(editada.get("regioes") or {})
            elif tipo == DocumentoTipo.DIARIO_BORDO:
                conteudo, pdf_engine_used = self._render_diario_html_ou_planilha(payload, formato)
            elif formato == DocumentoFormato.DOCX:
                conteudo = self._render_docx(
                    template_def, docx_ctx, template_path_override=docx_template_path
                )
            else:
                conteudo, pdf_engine_used = self._render_pdf(
                    tipo,
                    template_def,
                    payload,
                    docxtpl_context=docxtpl_context,
                    docx_template_path=docx_template_path,
                )

        digest = hashlib.sha256(conteudo).hexdigest()
        nome = build_document_filename(tipo, formato, reference=reference)
        result = DocumentoGerado(
            tipo=tipo,
            formato=formato,
            nome_arquivo=nome,
            content_type=get_content_type_for_format(formato),
            conteudo=conteudo,
            hash_sha256=digest,
            pdf_engine_used=pdf_engine_used,
        )
        if should_persist:
            from documentos.services.persistence import persist_geracao

            artifact = persist_geracao(
                result, servidor_id=servidor_id, roteiro_id=roteiro_id, oficio_id=oficio_id, termo_id=termo_id, prestacao_id=prestacao_id,
                ordem_servico_id=ordem_servico_id, plano_trabalho_id=plano_trabalho_id,
                criado_por_id=actor_id, payload_snapshot=payload,
                cache_key=artifact_cache_key,
            )
            result = replace(result, artefato_id=artifact.pk)
        return result

    def _render_diario_html_ou_planilha(self, payload, formato):
        """O PDF do diário nasce do HTML (como os demais documentos); a planilha
        continua saindo do modelo .xlsx. Sem o motor HTML, em desenvolvimento,
        o PDF volta a sair da planilha convertida."""
        from documentos.services.pdf_renderer import tipo_e_html_nativo

        if formato == DocumentoFormato.PDF and tipo_e_html_nativo(DocumentoTipo.DIARIO_BORDO):
            resultado = self._render_pdf_html(DocumentoTipo.DIARIO_BORDO, payload, docxtpl_context=None)
            if resultado is not None:
                return resultado
        return self._render_diario(payload, formato)

    def _render_diario(self, payload, formato):
        from pathlib import Path
        from documentos.services.adapters.xlsx_render import fill_diario_bordo_xlsx
        from documentos.services.adapters.excel_pdf import convert_xlsx_to_pdf_excel_com
        from documentos.services.adapters.libreoffice_pdf import convert_xlsx_to_pdf_libreoffice
        planilha = fill_diario_bordo_xlsx(
            template_path=Path(settings.BASE_DIR) / "documentos/resources/diario_bordo.xlsx",
            header=payload["header"], trechos=payload["trechos"],
        )
        if formato == DocumentoFormato.XLSX:
            return planilha, None
        explicit = getattr(settings, "DOCUMENTOS_DEFAULT_PDF_ENGINE", "auto")
        resolution = resolve_pdf_engine(explicit_setting=explicit, prefer_docx_pipeline=True)
        last_error = None
        for engine in resolution.attempt_chain:
            try:
                if engine == "word_com":
                    return convert_xlsx_to_pdf_excel_com(planilha), "excel_com"
                if engine == "libreoffice":
                    binary = resolve_libreoffice_binary()
                    if binary:
                        return convert_xlsx_to_pdf_libreoffice(xlsx_bytes=planilha, libreoffice_binary=binary), engine
            except Exception as exc:
                last_error = exc
                logger.warning("Conversão do diário via %s falhou: %s", engine, exc)
        raise DocumentValidationError("Não foi possível converter o diário de bordo para PDF. É necessário Excel ou LibreOffice.") from last_error

    def _validate_payload(
        self,
        tipo: DocumentoTipo,
        payload: Mapping[str, object],
    ) -> None:
        v = self._validators.validate(tipo, payload)
        if not v.ok:
            raise DocumentValidationError("; ".join(v.errors))
        req = ensure_required_fields(payload, canonical_required_keys(tipo))
        if not req.ok:
            raise DocumentValidationError("; ".join(req.errors))

    def _render_docx(
        self,
        template_def: DocumentTemplateDefinition,
        payload: Mapping[str, object],
        *,
        template_path_override: str | None = None,
    ) -> bytes:
        template_path = template_path_override or template_def.template_path
        path = resolve_resource_docx(template_path)
        if not path.exists():
            raise FileNotFoundError(f"Template DOCX ausente: {path}")
        with measure_step(
            "render_docx",
            {"template_path": template_path},
        ):
            return render_docx_bytes(template_path=path, context=payload)

    def _render_docx_bytes_for_tipo(
        self,
        tipo: DocumentoTipo,
        *,
        docxtpl_context: Mapping[str, object] | None,
        payload: Mapping[str, object],
        template_path_override: str | None = None,
    ) -> bytes:
        docx_def = self._templates.get(tipo, DocumentoFormato.DOCX)
        docx_ctx = docxtpl_context if docxtpl_context is not None else payload
        return self._render_docx(docx_def, docx_ctx, template_path_override=template_path_override)

    def _render_pdf(
        self,
        tipo: DocumentoTipo,
        template_def: DocumentTemplateDefinition,
        payload: Mapping[str, object],
        *,
        docxtpl_context: Mapping[str, object] | None = None,
        docx_template_path: str | None = None,
    ) -> tuple[bytes, str]:
        from documentos.services.pdf_renderer import tipo_e_html_nativo

        if tipo_e_html_nativo(tipo):
            resultado = self._render_pdf_html(tipo, payload, docxtpl_context=docxtpl_context)
            if resultado is not None:
                return resultado

        explicit = (getattr(settings, "DOCUMENTOS_DEFAULT_PDF_ENGINE", "auto") or "auto").strip().lower()
        if explicit not in (
            "auto",
            "word_com",
            "libreoffice",
            "weasyprint",
            "simple",
            "simple_fallback",
        ):
            raise DocumentValidationError(f"Motor PDF desconhecido: {explicit}")

        prefer_docx = docxtpl_context is not None
        if tipo == DocumentoTipo.OFICIO and not getattr(settings, "DOCUMENTOS_OFICIO_PDF_VIA_DOCX", True):
            prefer_docx = False

        with measure_step("_render_pdf", {"tipo": tipo.value}):
            with measure_step(
                "resolve_pdf_engine",
                {"tipo": tipo.value, "explicit": explicit, "prefer_docx": prefer_docx},
            ):
                resolution = resolve_pdf_engine(
                    explicit_setting=explicit,
                    prefer_docx_pipeline=prefer_docx,
                )

            if not resolution.attempt_chain:
                raise DocumentValidationError(build_pdf_unavailable_message(resolution))

            docx_cache: bytes | None = None

            def _docx_bytes() -> bytes:
                nonlocal docx_cache
                if docx_cache is None:
                    docx_cache = self._render_docx_bytes_for_tipo(
                        tipo,
                        docxtpl_context=docxtpl_context,
                        payload=payload,
                        template_path_override=docx_template_path,
                    )
                return docx_cache

            last_error: BaseException | None = None
            for eng in resolution.attempt_chain:
                try:
                    if eng == "word_com":
                        from documentos.services.adapters.word_pdf import convert_docx_to_pdf_word_com

                        with measure_step(
                            "convert_docx_to_pdf",
                            {"engine": "word_com", "tipo": tipo.value},
                        ):
                            return convert_docx_to_pdf_word_com(_docx_bytes()), "word_com"
                    if eng == "libreoffice":
                        with measure_step(
                            "convert_docx_to_pdf",
                            {"engine": "libreoffice", "tipo": tipo.value},
                        ):
                            return (
                                self._pdf_via_libreoffice(
                                    tipo,
                                    payload,
                                    docxtpl_context=docxtpl_context,
                                    docx_bytes=_docx_bytes(),
                                ),
                                "libreoffice",
                            )
                    if eng == "weasyprint":
                        from documentos.services.adapters.weasyprint_pdf import render_pdf_bytes_weasyprint

                        with measure_step(
                            "render_pdf_weasyprint",
                            {"engine": "weasyprint", "tipo": tipo.value},
                        ):
                            return (
                                render_pdf_bytes_weasyprint(
                                    html_template_name=template_def.template_path,
                                    context=payload,
                                    stylesheet_paths=template_def.stylesheet_paths,
                                ),
                                "weasyprint",
                            )
                    if eng == "simple_fallback":
                        from documentos.services.adapters.simple_pdf_fallback import render_simple_pdf_bytes

                        with measure_step(
                            "render_pdf_simple_fallback",
                            {"engine": "simple_fallback", "tipo": tipo.value},
                        ):
                            return render_simple_pdf_bytes(tipo=tipo, payload=payload), "simple_fallback"
                except Exception as exc:
                    last_error = exc
                    logger.warning("Motor PDF %s falhou para %s: %s", eng, tipo.value, exc, exc_info=True)
                    continue

            msg = build_pdf_unavailable_message(resolution)
            if last_error is not None:
                raise DocumentValidationError(msg) from last_error
            raise DocumentValidationError(msg)

    def _render_pdf_html(
        self,
        tipo: DocumentoTipo,
        payload: Mapping[str, object],
        *,
        docxtpl_context: Mapping[str, object] | None,
    ) -> tuple[bytes, str] | None:
        """PDF direto do HTML institucional, sem DOCX no caminho.

        Devolve `None` só quando o motor não está disponível e a contingência
        de desenvolvimento está ligada: aí a façade segue pela cadeia antiga,
        avisando no log. Em produção a indisponibilidade é erro — o PDF nunca
        deve nascer do DOCX por acidente.
        """
        from documentos.services.document_context import contexto_de_payload
        from documentos.services.exceptions import DocumentRendererUnavailable
        from documentos.services.pdf_renderer import render_pdf, renderizar_html

        contexto = contexto_de_payload(tipo, payload, docxtpl_context, modo="pdf")
        html = renderizar_html(tipo, contexto, modo="pdf")
        try:
            return render_pdf(html, tipo=tipo), "html_weasyprint"
        except DocumentRendererUnavailable as exc:
            contingencia = getattr(settings, "DOCUMENTOS_PDF_HTML_FALLBACK_DOCX", getattr(settings, "DEBUG", False))
            if contingencia:
                logger.warning("Motor HTML→PDF indisponível para %s (%s); seguindo pela cadeia antiga.", tipo.value, exc)
                return None
            raise DocumentValidationError(str(exc)) from exc

    def _pdf_via_libreoffice(
        self,
        tipo: DocumentoTipo,
        payload: Mapping[str, object],
        *,
        libreoffice_binary: str | None = None,
        docxtpl_context: Mapping[str, object] | None = None,
        docx_bytes: bytes | None = None,
    ) -> bytes:
        if docx_bytes is None:
            docx_bytes = self._render_docx_bytes_for_tipo(
                tipo,
                docxtpl_context=docxtpl_context,
                payload=payload,
            )
        binary = (libreoffice_binary or "").strip() or resolve_libreoffice_binary(verify_version=True)
        if not binary:
            raise DocumentValidationError(
                "Motor PDF = libreoffice, mas nenhum executável foi encontrado. "
                "Defina DOCUMENTOS_LIBREOFFICE_BINARY no .env ou instale o LibreOffice.",
            )
        return convert_docx_to_pdf_libreoffice(docx_bytes=docx_bytes, libreoffice_binary=binary)

    def converter_docx_pronto_para_pdf(
        self,
        docx_bytes: bytes,
        *,
        tipo: DocumentoTipo,
    ) -> tuple[bytes, str]:
        """Converte um DOCX já montado sem renderizá-lo novamente.

        Usado por lotes: todos os documentos são unidos como DOCX e passam uma
        única vez pelo conversor persistente.
        """
        explicit = (
            getattr(settings, "DOCUMENTOS_DEFAULT_PDF_ENGINE", "auto") or "auto"
        ).strip().lower()
        resolution = resolve_pdf_engine(
            explicit_setting=explicit,
            prefer_docx_pipeline=True,
        )
        last_error: BaseException | None = None
        for engine in resolution.attempt_chain:
            try:
                if engine == "libreoffice":
                    return (
                        self._pdf_via_libreoffice(
                            tipo,
                            {},
                            docx_bytes=docx_bytes,
                        ),
                        engine,
                    )
                if engine == "word_com":
                    from documentos.services.adapters.word_pdf import (
                        convert_docx_to_pdf_word_com,
                    )

                    return convert_docx_to_pdf_word_com(docx_bytes), engine
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Conversor DOCX em lote %s falhou para %s: %s",
                    engine,
                    tipo.value,
                    exc,
                    exc_info=True,
                )

        message = build_pdf_unavailable_message(resolution)
        if last_error is not None:
            raise DocumentValidationError(message) from last_error
        raise DocumentValidationError(message)


def build_default_facade() -> DocumentoFacade:
    return DocumentoFacade()
