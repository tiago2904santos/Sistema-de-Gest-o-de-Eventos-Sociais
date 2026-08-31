"""Regras de negócio do módulo de Coffee Break.

Concentra o que precisa ser testável fora das views: a derivação da
situação financeira e a validação transacional do saldo do lote.
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from .models import LoteCoffeeBreak, SituacaoFinanceira

# Situação -> sufixo dos status-badges já existentes no design system.
CSS_SITUACAO = {
    SituacaoFinanceira.AGUARDANDO_NOTA_FISCAL: "aguardando_despacho",
    SituacaoFinanceira.AGUARDANDO_PROTOCOLO: "aguardando_despacho",
    SituacaoFinanceira.AGUARDANDO_ATESTO: "aguardando_despacho",
    SituacaoFinanceira.AGUARDANDO_ORDEM_BANCARIA: "deferida_em_andamento",
    SituacaoFinanceira.AGUARDANDO_ENVIO_EMPRESA: "deferida_em_andamento",
    SituacaoFinanceira.CONCLUIDA: "atendida",
    SituacaoFinanceira.CANCELADA: "cancelada",
}


def situacao_financeira(solicitacao):
    """Deriva a situação do fluxo de pagamento a partir dos marcos.

    A planilha não tem coluna de status: a leitura é feita pelos campos
    preenchidos, na ordem do fluxo real — NF → protocolo → atesto →
    ordem bancária → envio à empresa.
    """
    if solicitacao.cancelada:
        return SituacaoFinanceira.CANCELADA
    if solicitacao.data_envio_empresa:
        return SituacaoFinanceira.CONCLUIDA
    if solicitacao.data_ordem_bancaria:
        return SituacaoFinanceira.AGUARDANDO_ENVIO_EMPRESA
    if solicitacao.data_atesto_gaf:
        return SituacaoFinanceira.AGUARDANDO_ORDEM_BANCARIA
    if solicitacao.protocolo_pagamento.strip():
        return SituacaoFinanceira.AGUARDANDO_ATESTO
    if solicitacao.numero_nota_fiscal.strip():
        return SituacaoFinanceira.AGUARDANDO_PROTOCOLO
    return SituacaoFinanceira.AGUARDANDO_NOTA_FISCAL


def validar_saldo(lote, quantidade, excluir_pk=None):
    """Garante que a quantidade cabe no saldo do lote.

    Deve rodar dentro de uma transação com o lote travado
    (``select_for_update``) para não haver corrida entre solicitações
    simultâneas — use :func:`salvar_com_saldo`.
    """
    consumo = lote.solicitacoes.filter(cancelada=False)
    if excluir_pk:
        consumo = consumo.exclude(pk=excluir_pk)
    consumido = consumo.aggregate(total=models.Sum("quantidade"))["total"] or 0
    restante = lote.quantidade_total - consumido
    if quantidade > restante:
        raise ValidationError(
            {
                "quantidade": (
                    f"Quantidade acima do saldo do lote: restam {restante} "
                    f"de {lote.quantidade_total} unidades."
                )
            }
        )


def salvar_com_saldo(solicitacao):
    """Salva a solicitação consumindo saldo com trava no lote.

    Trava a linha do lote, revalida o saldo já com concorrentes
    serializados e só então persiste — a validação e a escrita ficam na
    mesma transação.
    """
    with transaction.atomic():
        lote = LoteCoffeeBreak.objects.select_for_update().get(
            pk=solicitacao.lote_id
        )
        if not solicitacao.cancelada:
            validar_saldo(lote, solicitacao.quantidade, excluir_pk=solicitacao.pk)
        solicitacao.save()
    return solicitacao


def cancelar(solicitacao, usuario, motivo=""):
    """Cancelamento auditável: sai do consumo, mas permanece no histórico."""
    if solicitacao.cancelada:
        raise ValidationError("A solicitação já está cancelada.")
    solicitacao.cancelada = True
    solicitacao.cancelada_em = timezone.now()
    solicitacao.cancelada_por = usuario
    solicitacao.motivo_cancelamento = (motivo or "").strip()[:255]
    solicitacao.save(
        update_fields=[
            "cancelada",
            "cancelada_em",
            "cancelada_por",
            "motivo_cancelamento",
            "atualizado_em",
        ]
    )
    return solicitacao


def reativar(solicitacao):
    """Desfaz um cancelamento, revalidando o saldo do lote."""
    if not solicitacao.cancelada:
        raise ValidationError("A solicitação não está cancelada.")
    if (solicitacao.quantidade or 0) < 1:
        raise ValidationError(
            "Informe uma quantidade válida antes de reativar a solicitação."
        )
    with transaction.atomic():
        lote = LoteCoffeeBreak.objects.select_for_update().get(
            pk=solicitacao.lote_id
        )
        validar_saldo(lote, solicitacao.quantidade, excluir_pk=solicitacao.pk)
        solicitacao.cancelada = False
        solicitacao.cancelada_em = None
        solicitacao.cancelada_por = None
        solicitacao.motivo_cancelamento = ""
        solicitacao.save(
            update_fields=[
                "cancelada",
                "cancelada_em",
                "cancelada_por",
                "motivo_cancelamento",
                "atualizado_em",
            ]
        )
    return solicitacao


# Percentual de saldo abaixo do qual o painel destaca o lote.
LIMIAR_ALERTA_SALDO = 15


def lotes_em_alerta(lotes_anotados):
    """Lotes ativos com saldo igual ou abaixo do limiar de alerta."""
    em_alerta = []
    for lote in lotes_anotados:
        if not lote.quantidade_total:
            continue
        percentual_restante = lote.restante * 100 / lote.quantidade_total
        if percentual_restante <= LIMIAR_ALERTA_SALDO:
            em_alerta.append(lote)
    return em_alerta
