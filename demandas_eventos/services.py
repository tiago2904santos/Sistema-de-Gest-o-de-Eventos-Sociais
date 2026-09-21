"""Andamento e histórico das palestras e eventos da ASCOM.

O status não é mais um campo solto do formulário: como nas Solicitações de
evento, ele anda por ações registradas — cada mudança leva a anotação de
andamento (a coluna "Andamento" da planilha) e fica no histórico.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AcaoHistoricoDemanda, HistoricoDemanda, StatusDemanda

# O que cada status diz, no cartão de escolha da tela.
DICAS = {
    StatusDemanda.PENDENTE: "Recebida, ainda sem tratativa",
    StatusDemanda.EM_ANDAMENTO: "Tratando com o solicitante e o palestrante",
    StatusDemanda.AGUARDANDO_RETORNO: "Esperando resposta do solicitante",
    StatusDemanda.EVENTO_AGENDADO: "Data e palestrante confirmados",
    StatusDemanda.ATENDIDA: "Palestra ou evento realizado",
    StatusDemanda.CANCELADA: "Não vai acontecer",
}

# As etapas do acompanhamento (stepper), na ordem do fluxo. "Aguardando
# retorno" é uma pausa dentro de "Em andamento", não uma etapa própria.
ETAPAS = [
    ("Recebida", {StatusDemanda.PENDENTE}),
    ("Em andamento", {StatusDemanda.EM_ANDAMENTO, StatusDemanda.AGUARDANDO_RETORNO}),
    ("Agendada", {StatusDemanda.EVENTO_AGENDADO}),
    ("Atendida", {StatusDemanda.ATENDIDA}),
]


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


def opcoes_de_status(demanda, icones):
    """Os status para onde a linha pode ir: todos, menos o atual."""
    return [
        {"valor": valor, "rotulo": rotulo, "dica": DICAS[valor], "icone": icones[valor]}
        for valor, rotulo in StatusDemanda.choices
        if valor != demanda.status
    ]


def etapas(demanda):
    """O stepper do acompanhamento: concluídas, a atual e as que faltam."""
    atual = next((i for i, (_, grupo) in enumerate(ETAPAS) if demanda.status in grupo), None)
    saida = []
    for i, (titulo, grupo) in enumerate(ETAPAS):
        if demanda.status == StatusDemanda.ATENDIDA or (atual is not None and i < atual):
            estado = "concluido"
        elif i == atual:
            estado = "atual"
        else:
            estado = "pendente"
        rotulo = titulo
        if i == 1 and demanda.status == StatusDemanda.AGUARDANDO_RETORNO:
            rotulo = "Aguardando retorno"
        saida.append({"titulo": rotulo, "estado": estado})
    return saida


def ultima_anotacao(demanda):
    """A anotação da última mudança de status, ou a da planilha se não houve."""
    ultima = demanda.historico.filter(acao=AcaoHistoricoDemanda.TRANSICAO).order_by("-criado_em", "-pk").first()
    if ultima is None:
        return demanda.andamento
    return ultima.descricao


@transaction.atomic
def registrar_andamento(demanda, usuario, novo_status, andamento=""):
    """Muda o status e grava a anotação de andamento, com rastro no histórico."""
    andamento = (andamento or "").strip()
    if novo_status not in StatusDemanda.values or novo_status == demanda.status:
        raise ValidationError("Escolha o novo status.")
    anterior = demanda.status
    demanda.status = novo_status
    if andamento:
        # A coluna "Andamento" da planilha guarda a anotação mais recente.
        demanda.andamento = andamento
    demanda.atualizado_em = timezone.now()
    demanda.save(update_fields=["status", "andamento", "atualizado_em"])
    registrar_historico(
        demanda,
        usuario,
        AcaoHistoricoDemanda.TRANSICAO,
        andamento,
        status_anterior=anterior,
        status_novo=novo_status,
    )
    return demanda
