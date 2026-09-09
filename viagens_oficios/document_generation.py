"""Geração síncrona: contexto do GV e persistência/cache da façade da F3."""
from django.core.exceptions import ValidationError
from documentos.services.facade import DocumentoFacade
from documentos.services.types import DocumentoTipo
from .models import Oficio
from .services import reservar_numero_oficio, validar_oficio_para_documento
from .documents import build_canonical_document_payload
from .docxtpl_context import build_oficio_docxtpl_context, build_justificativa_docxtpl_context


def gerar_documento(oficio, formato, tipo=DocumentoTipo.OFICIO):
    if oficio.cancelado:
        raise ValidationError("Reative o ofício antes de emitir documentos.")
    avaliacao = validar_oficio_para_documento(oficio)
    if avaliacao['pendencias']:
        raise ValidationError(avaliacao['pendencias'])
    reservar_numero_oficio(oficio, ano=oficio.data_criacao.year)
    payload = build_canonical_document_payload(oficio, tipo)
    contexto = (build_oficio_docxtpl_context(oficio) if tipo == DocumentoTipo.OFICIO
                else build_justificativa_docxtpl_context(oficio))
    resultado = DocumentoFacade().gerar(tipo=tipo, formato=formato, payload=payload,
        reference=oficio.numero_formatado.replace('/', '-'), docxtpl_context=contexto,
        oficio_id=oficio.pk, roteiro_id=oficio.roteiro_id)
    if oficio.status == Oficio.STATUS_RASCUNHO:
        oficio.status = Oficio.STATUS_GERADO
        oficio.save(update_fields=['status', 'atualizado_em'])
    return resultado
