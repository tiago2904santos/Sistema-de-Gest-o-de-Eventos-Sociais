"""Indicadores do módulo de Atendimento à Imprensa — painel e hub."""

import datetime as dt

from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.dateformat import format as formatar_data

from .models import (
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
