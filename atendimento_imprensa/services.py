"""Indicadores do módulo de Atendimento à Imprensa — painel e hub."""

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.dateformat import format as formatar_data

from core.andamento import Fluxo

from .models import (
    AcaoHistorico,
    HistoricoAtendimento,
    SITUACOES_ABERTAS,
    Atendimento,
    SituacaoAtendimento,
)


def inicio_do_mes(hoje=None):
    hoje = hoje or timezone.localdate()
    return hoje.replace(day=1)


def resumo_periodo(inicio, fim=None):
    qs = Atendimento.objects.filter(data__gte=inicio)
    if fim:
        qs = qs.filter(data__lte=fim)
    return qs.aggregate(
        total=Count("pk"),
        atendidos=Count("pk", filter=Q(situacao=SituacaoAtendimento.ATENDIDO)),
        abertos=Count("pk", filter=Q(situacao__in=SITUACOES_ABERTAS)),
        aguardando_fonte=Count(
            "pk", filter=Q(situacao=SituacaoAtendimento.AGUARDANDO_FONTE)
        ),
        nao_responder=Count(
            "pk", filter=Q(situacao=SituacaoAtendimento.NAO_RESPONDER)
        ),
    )


def em_aberto():
    return Atendimento.objects.filter(situacao__in=SITUACOES_ABERTAS)


def deadline_vencido(hoje=None):
    hoje = hoje or timezone.localdate()
    return em_aberto().filter(deadline__lt=hoje)


def por_veiculo(inicio, fim=None, limite=8):
    qs = Atendimento.objects.filter(data__gte=inicio, veiculo__isnull=False)
    if fim:
        qs = qs.filter(data__lte=fim)
    return list(
        qs.values(nome=F("veiculo__nome"), pk=F("veiculo_id"))
        .annotate(total=Count("pk"))
        .order_by("-total", "nome")[:limite]
    )


def por_responsavel(inicio, fim=None, limite=8):
    qs = Atendimento.objects.filter(data__gte=inicio, responsavel__isnull=False)
    if fim:
        qs = qs.filter(data__lte=fim)
    return list(
        qs.values(nome=F("responsavel__nome"), pk=F("responsavel_id"))
        .annotate(
            total=Count("pk"),
            atendidos=Count("pk", filter=Q(situacao=SituacaoAtendimento.ATENDIDO)),
        )
        .order_by("-total", "nome")[:limite]
    )


def serie_mensal(meses=6, hoje=None):
    hoje = hoje or timezone.localdate()
    primeiro = hoje.replace(day=1)
    marcos = []
    for _ in range(meses):
        marcos.append(primeiro)
        primeiro = (primeiro - dt.timedelta(days=1)).replace(day=1)
    marcos.reverse()
    contagens = {
        (linha["ano"], linha["mes"]): linha["total"]
        for linha in Atendimento.objects.filter(data__gte=marcos[0])
        .values(ano=F("data__year"), mes=F("data__month"))
        .annotate(total=Count("pk"))
    }
    barras = [
        {
            "rotulo": formatar_data(marco, "M/y"),
            "titulo": formatar_data(marco, r"F \d\e Y"),
            "valor": contagens.get((marco.year, marco.month), 0),
        }
        for marco in marcos
    ]
    maximo = max((b["valor"] for b in barras), default=0) or 1
    for barra in barras:
        barra["altura"] = round(barra["valor"] * 100 / maximo)
    return barras


# ---------------------------------------------------------------------------
# Andamento e histórico do atendimento (desenho das Palestras)
# ---------------------------------------------------------------------------


_S = SituacaoAtendimento
FLUXO = Fluxo(
    choices=_S.choices,
    dicas={
        _S.EM_ANDAMENTO: "Tratando o pedido",
        _S.EM_ANDAMENTO_TEXTO: "Preparando a resposta por escrito",
        _S.EM_ANDAMENTO_VIDEO: "Preparando gravação ou entrevista",
        _S.AGUARDANDO_FONTE: "Esperando a fonte responder",
        _S.AGUARDANDO_PRODUTORA: "Esperando a produção do veículo",
        _S.AGUARDAR_NOVA_SOLICITACAO: "O jornalista vai voltar a pedir",
        _S.PROXIMO_MES: "Fica para o mês que vem",
        _S.ATENDIDO: "Resposta enviada ao jornalista",
        _S.NAO_RESPONDER: "A assessoria não vai atender",
    },
    icones={
        _S.EM_ANDAMENTO: "activity",
        _S.EM_ANDAMENTO_TEXTO: "document",
        _S.EM_ANDAMENTO_VIDEO: "eye",
        _S.AGUARDANDO_FONTE: "hourglass",
        _S.AGUARDANDO_PRODUTORA: "hourglass",
        _S.AGUARDAR_NOVA_SOLICITACAO: "clock",
        _S.PROXIMO_MES: "calendar",
        _S.ATENDIDO: "check-circle",
        _S.NAO_RESPONDER: "ban",
    },
    etapas=[
        ("Pedido recebido", set()),
        ("Em andamento", {_S.EM_ANDAMENTO, _S.EM_ANDAMENTO_TEXTO, _S.EM_ANDAMENTO_VIDEO}),
        ("Aguardando", {_S.AGUARDANDO_FONTE, _S.AGUARDANDO_PRODUTORA, _S.AGUARDAR_NOVA_SOLICITACAO, _S.PROXIMO_MES}),
        ("Atendido", {_S.ATENDIDO}),
    ],
    encerrados={_S.NAO_RESPONDER},
    concluido=_S.ATENDIDO,
)


def registrar_historico(atendimento, usuario, acao, descricao="", status_anterior="", status_novo=""):
    return HistoricoAtendimento.objects.create(
        atendimento=atendimento,
        usuario=usuario,
        acao=acao,
        descricao=(descricao or "").strip(),
        status_anterior=status_anterior,
        status_novo=status_novo,
    )


def ultima_anotacao(atendimento):
    ultima = atendimento.historico.filter(acao=AcaoHistorico.TRANSICAO).order_by("-criado_em", "-pk").first()
    return atendimento.andamento if ultima is None else ultima.descricao


@transaction.atomic
def registrar_andamento(atendimento, usuario, nova_situacao, andamento=""):
    """Muda a situação com a anotação de andamento e deixa o rastro no histórico."""
    andamento = (andamento or "").strip()
    if nova_situacao not in _S.values or nova_situacao == atendimento.situacao:
        raise ValidationError("Escolha a nova situação.")
    if nova_situacao == _S.ATENDIDO and not (andamento or atendimento.resposta or atendimento.andamento):
        raise ValidationError(
            "Para marcar como atendido, escreva o andamento ou registre a resposta enviada."
        )
    anterior = atendimento.situacao
    atendimento.situacao = nova_situacao
    if andamento:
        atendimento.andamento = andamento
    atendimento.save(update_fields=["situacao", "andamento", "atualizado_em"])
    registrar_historico(
        atendimento, usuario, AcaoHistorico.TRANSICAO, andamento,
        status_anterior=anterior, status_novo=nova_situacao,
    )
    return atendimento
