"""Indicadores do módulo de Publicações — usados pelo painel e pelo hub."""

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.dateformat import format as formatar_data

from core.andamento import Fluxo

from .models import (
    AcaoHistorico,
    HistoricoPublicacao,
    Publicacao,
    StatusPublicacao,
    formatar_duracao,
)


def inicio_do_mes(hoje=None):
    hoje = hoje or timezone.localdate()
    return hoje.replace(day=1)


def resumo_periodo(inicio, fim=None):
    """Contagens do período [inicio, fim] por status."""
    qs = Publicacao.objects.filter(data__gte=inicio)
    if fim:
        qs = qs.filter(data__lte=fim)
    contagem = qs.aggregate(
        total=Count("pk"),
        publicadas=Count("pk", filter=Q(status=StatusPublicacao.PUBLICADA)),
        pendentes=Count(
            "pk",
            filter=Q(
                status__in=[StatusPublicacao.PENDENTE, StatusPublicacao.EM_ANDAMENTO]
            ),
        ),
        canceladas=Count("pk", filter=Q(status=StatusPublicacao.CANCELADA)),
        sesp=Count("pk", filter=Q(enviado_sesp=True)),
        aen=Count("pk", filter=Q(publicado_aen=True)),
    )
    return contagem


def em_aberto():
    return Publicacao.objects.filter(
        status__in=[StatusPublicacao.PENDENTE, StatusPublicacao.EM_ANDAMENTO]
    )


def tempo_medio_publicacao(inicio, fim=None):
    """Média (timedelta) entre início da pauta e publicação no período."""
    qs = Publicacao.objects.filter(
        data__gte=inicio,
        status=StatusPublicacao.PUBLICADA,
        inicio_pauta__isnull=False,
        horario_publicacao__isnull=False,
        data_publicacao__isnull=False,
    )
    if fim:
        qs = qs.filter(data__lte=fim)
    total = dt.timedelta()
    quantidade = 0
    for pauta in qs.only(
        "data", "inicio_pauta", "data_publicacao", "horario_publicacao"
    ):
        delta = pauta.tempo_ate_publicacao
        if delta is not None:
            total += delta
            quantidade += 1
    if not quantidade:
        return None, 0
    return total / quantidade, quantidade


def tempo_medio_display(inicio, fim=None):
    media, quantidade = tempo_medio_publicacao(inicio, fim)
    if media is None:
        return "—", 0
    return formatar_duracao(media), quantidade


def por_jornalista(inicio, fim=None, limite=8):
    qs = Publicacao.objects.filter(data__gte=inicio)
    if fim:
        qs = qs.filter(data__lte=fim)
    return list(
        qs.values(nome=F("jornalista__nome"), pk=F("jornalista_id"))
        .annotate(
            total=Count("pk"),
            publicadas=Count("pk", filter=Q(status=StatusPublicacao.PUBLICADA)),
        )
        .order_by("-total", "nome")[:limite]
    )


def por_unidade(inicio, fim=None, limite=8):
    qs = Publicacao.objects.filter(data__gte=inicio, unidade__isnull=False)
    if fim:
        qs = qs.filter(data__lte=fim)
    return list(
        qs.values(nome=F("unidade__nome"), pk=F("unidade_id"))
        .annotate(total=Count("pk"))
        .order_by("-total", "nome")[:limite]
    )


def serie_mensal(meses=6, hoje=None):
    """Publicações por mês (últimos ``meses``), para o gráfico de barras."""
    hoje = hoje or timezone.localdate()
    primeiro = hoje.replace(day=1)
    marcos = []
    for _ in range(meses):
        marcos.append(primeiro)
        primeiro = (primeiro - dt.timedelta(days=1)).replace(day=1)
    marcos.reverse()
    contagens = {
        (linha["ano"], linha["mes"]): linha["total"]
        for linha in Publicacao.objects.filter(data__gte=marcos[0])
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
# Andamento e histórico da pauta (desenho das Palestras)
# ---------------------------------------------------------------------------


FLUXO = Fluxo(
    choices=StatusPublicacao.choices,
    dicas={
        StatusPublicacao.PENDENTE: "Pauta recebida, ainda sem redação",
        StatusPublicacao.EM_ANDAMENTO: "Em apuração, redação ou edição",
        StatusPublicacao.PUBLICADA: "Matéria no ar no site da PCPR",
        StatusPublicacao.CANCELADA: "A pauta não vai sair",
    },
    icones={
        StatusPublicacao.PENDENTE: "hourglass",
        StatusPublicacao.EM_ANDAMENTO: "activity",
        StatusPublicacao.PUBLICADA: "check-circle",
        StatusPublicacao.CANCELADA: "ban",
    },
    etapas=[
        ("Pauta recebida", {StatusPublicacao.PENDENTE}),
        ("Em andamento", {StatusPublicacao.EM_ANDAMENTO}),
        ("Publicada", {StatusPublicacao.PUBLICADA}),
    ],
    encerrados={StatusPublicacao.CANCELADA},
    concluido=StatusPublicacao.PUBLICADA,
)


def registrar_historico(publicacao, usuario, acao, descricao="", status_anterior="", status_novo=""):
    return HistoricoPublicacao.objects.create(
        publicacao=publicacao,
        usuario=usuario,
        acao=acao,
        descricao=(descricao or "").strip(),
        status_anterior=status_anterior,
        status_novo=status_novo,
    )


def ultima_anotacao(publicacao):
    """A anotação da última mudança de status, ou o andamento da planilha."""
    ultima = publicacao.historico.filter(acao=AcaoHistorico.TRANSICAO).order_by("-criado_em", "-pk").first()
    return publicacao.andamento if ultima is None else ultima.descricao


@transaction.atomic
def registrar_andamento(publicacao, usuario, novo_status, andamento=""):
    """Muda o status com a anotação de andamento e deixa o rastro no histórico.

    Ao marcar como publicada sem data, a publicação fica com a data e a hora
    do registro — dá para corrigir depois no formulário.
    """
    andamento = (andamento or "").strip()
    if novo_status not in StatusPublicacao.values or novo_status == publicacao.status:
        raise ValidationError("Escolha o novo status.")
    anterior = publicacao.status
    publicacao.status = novo_status
    campos = ["status", "andamento", "atualizado_em"]
    if andamento:
        publicacao.andamento = andamento
    if novo_status == StatusPublicacao.PUBLICADA and not publicacao.data_publicacao:
        agora = timezone.localtime()
        publicacao.data_publicacao = max(agora.date(), publicacao.data)
        publicacao.horario_publicacao = publicacao.horario_publicacao or agora.time().replace(second=0, microsecond=0)
        campos += ["data_publicacao", "horario_publicacao"]
    publicacao.save(update_fields=campos)
    registrar_historico(
        publicacao, usuario, AcaoHistorico.TRANSICAO, andamento,
        status_anterior=anterior, status_novo=novo_status,
    )
    return publicacao
