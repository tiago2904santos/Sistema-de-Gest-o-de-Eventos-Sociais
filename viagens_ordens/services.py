"""Exclusão com lacuna e geração do documento da Ordem de Serviço.

Da origem (`ordens_servico/services.py`): excluir registra o número liberado
para a próxima OS do ano reaproveitá-lo; o modelo DOCX é o `ordem_servico.docx`
para o tipo padrão e o `ordem_servico_modelos.docx` para os demais. A geração
passa pela façade documental da casa, que persiste o artefato e devolve a
versão assinada quando houver.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from core.deletion import excluir_com_protecao
from documentos.services.facade import DocumentoFacade
from documentos.services.types import DocumentoFormato, DocumentoTipo
from viagens_cadastros.selectors import build_configuracao_context

from .docxtpl_context import _destinos_display, _periodo_extenso, build_os_docxtpl_context
from .models import OrdemServico, OrdemServicoNumeroLacuna


@transaction.atomic
def excluir_ordem_servico(ordem: OrdemServico) -> None:
    """Exclui a OS e registra somente o número que ela efetivamente liberou."""
    numero, ano = ordem.numero, ordem.ano
    excluir_com_protecao(ordem)
    if numero and ano:
        OrdemServicoNumeroLacuna.objects.get_or_create(ano=ano, numero=numero)


def _template_ordem_servico(ordem: OrdemServico) -> str:
    if ordem.tipo_necessidade == OrdemServico.TIPO_PADRAO:
        return "ordem_servico.docx"
    return "ordem_servico_modelos.docx"


def referencia_da_ordem(ordem: OrdemServico) -> str:
    if ordem.numero and ordem.ano:
        return f"os-{ordem.numero:03d}-{ordem.ano}"
    return f"os-{ordem.pk}"


def resumo_da_ordem(ordem: OrdemServico) -> dict:
    """O que fica gravado no snapshot do artefato, para auditoria do que foi emitido."""
    return {
        "id": ordem.pk,
        "numero": ordem.numero_formatado,
        "tipo_necessidade": ordem.tipo_necessidade,
        "periodo": _periodo_extenso(ordem.data_evento_inicio, ordem.data_evento_fim),
        "destinos": _destinos_display(ordem),
        "servidores": [s.nome for s in ordem.servidores.all()],
        "funcoes_servidores": dict(ordem.funcoes_servidores or {}),
        "oficios": [o.numero_formatado for o in ordem.oficios.all()],
        "motivo": ordem.motivo or "",
    }


def gerar_ordem_servico(ordem: OrdemServico, formato: DocumentoFormato, *, usar_assinado: bool = True):
    """`usar_assinado=False` pede o arquivo original mesmo com PDF assinado anexado."""
    if ordem.cancelado:
        raise ValidationError("Reative a Ordem de Serviço antes de emitir documentos.")
    from documentos.services.document_blocks import conteudo_documental

    payload = {
        "institucional": build_configuracao_context(), "ordem_servico": resumo_da_ordem(ordem),
        # Os textos do modelo reescritos no editor: entram no PDF e na chave do cache.
        "documento": conteudo_documental(DocumentoTipo.ORDEM_SERVICO, ordem),
    }
    return DocumentoFacade().gerar(
        tipo=DocumentoTipo.ORDEM_SERVICO, formato=formato, payload=payload,
        reference=referencia_da_ordem(ordem), docxtpl_context=build_os_docxtpl_context(ordem),
        docx_template_path=_template_ordem_servico(ordem), ordem_servico_id=ordem.pk,
        usar_assinado=usar_assinado,
    )
