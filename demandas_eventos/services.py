"""Workflow e histórico das Demandas ASCOM."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import (
    AcaoHistoricoDemanda,
    HistoricoDemanda,
    StatusDemanda,
)
from .permissions import pode_editar, pode_ver


TRANSICOES = {
    StatusDemanda.PENDENTE: {
        StatusDemanda.EM_ANDAMENTO,
        StatusDemanda.AGUARDANDO_RETORNO,
        StatusDemanda.NAO_ATENDER,
        StatusDemanda.CANCELADA,
    },
    StatusDemanda.AGUARDANDO_RETORNO: {
        StatusDemanda.EM_ANDAMENTO,
        StatusDemanda.NAO_ATENDER,
        StatusDemanda.CANCELADA,
    },
    StatusDemanda.EM_ANDAMENTO: {
        StatusDemanda.AGUARDANDO_RETORNO,
        StatusDemanda.EVENTO_AGENDADO,
        StatusDemanda.ATENDIDA,
        StatusDemanda.NAO_ATENDER,
        StatusDemanda.CANCELADA,
    },
    StatusDemanda.EVENTO_AGENDADO: {
        StatusDemanda.EM_ANDAMENTO,
        StatusDemanda.ATENDIDA,
        StatusDemanda.CANCELADA,
    },
}

STATUS_COM_JUSTIFICATIVA = {
    StatusDemanda.NAO_ATENDER,
    StatusDemanda.CANCELADA,
}


def registrar_historico(
    demanda,
    usuario,
    acao,
    descricao="",
    status_anterior="",
    status_novo="",
):
    return HistoricoDemanda.objects.create(
        demanda=demanda,
        usuario=usuario,
        acao=acao,
        descricao=(descricao or "").strip(),
        status_anterior=status_anterior,
        status_novo=status_novo,
    )


def opcoes_transicao(demanda):
    rotulos = dict(StatusDemanda.choices)
    return [
        {"valor": status, "rotulo": rotulos[status]}
        for status in StatusDemanda.values
        if status in TRANSICOES.get(demanda.status, set())
    ]


@transaction.atomic
def transicionar(demanda, usuario, novo_status, justificativa=""):
    if not pode_ver(usuario, demanda):
        raise PermissionDenied
    permitidos = TRANSICOES.get(demanda.status, set())
    if novo_status not in permitidos:
        raise ValidationError("Esta mudança de status não é permitida.")
    justificativa = (justificativa or "").strip()
    if novo_status in STATUS_COM_JUSTIFICATIVA and not justificativa:
        raise ValidationError("Informe a justificativa para esta decisão.")
    anterior = demanda.status
    demanda.status = novo_status
    demanda.save(update_fields=["status", "atualizado_em"])
    registrar_historico(
        demanda,
        usuario,
        AcaoHistoricoDemanda.TRANSICAO,
        justificativa,
        status_anterior=anterior,
        status_novo=novo_status,
    )
    return demanda
