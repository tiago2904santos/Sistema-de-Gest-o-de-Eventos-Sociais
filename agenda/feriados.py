"""Feriados e pontos facultativos no calendário (m138).

Uma faixa de fundo no dia, não um compromisso: quem planeja palestra ou viagem
vê de relance que a sexta é Corpus Christi antes de marcar. Os nacionais vêm
calculados de ``core.feriados`` (fixos e móveis, pela Páscoa); os do Paraná e
os pontos facultativos da casa, do cadastro ``core.models.Feriado``; e os
municipais só das cidades onde há compromisso no período — o feriado de
Maringá aparece na semana em que alguém vai a Maringá, e não no calendário de
todo mundo o ano inteiro.

A mesma função (``core.feriados``) é a que conta dias úteis nos prazos, então
o que a Agenda mostra como feriado é o que o prazo pula.
"""

from __future__ import annotations

import datetime as dt

from .fontes import Fonte


def _pode(usuario) -> bool:
    return bool(usuario and usuario.is_authenticated)


def _municipios_do_periodo(usuario, inicio, fim) -> set[int]:
    """As cidades com compromisso no período: destinos das viagens (e dos seus
    roteiros), das solicitações e das palestras que a pessoa pode ver."""
    from demandas_eventos import permissions as perm_demandas
    from demandas_eventos.models import DemandaEvento
    from solicitacoes import permissions as perm_solicitacoes
    from solicitacoes.models import SolicitacaoEvento
    from viagens_cadastros.permissions import pode_acessar as pode_viagens
    from viagens_roteiros.models import RoteiroDestino
    from viagens_viagem.models import Viagem

    from .fontes import _sobrepoe

    pks: set[int] = set()
    if pode_viagens(usuario):
        viagens = Viagem.objects.filter(_sobrepoe("data_inicio", "data_fim", inicio, fim), cancelado=False)
        for v in viagens.only("destino_estado", "destino_municipio", "destinos_extras"):
            pks.update(m for _e, m in v.destinos_pares() if m)
        destinos = RoteiroDestino.objects.filter(roteiro__cancelado=False).filter(
            models_q_roteiro_da_viagem(viagens)
        )
        pks.update(destinos.values_list("municipio_id", flat=True))
    solicitacoes = perm_solicitacoes.queryset_visivel(usuario, SolicitacaoEvento.objects.all()).filter(
        data_inicio_evento__isnull=False, municipio__isnull=False,
    ).filter(_sobrepoe("data_inicio_evento", "data_fim_evento", inicio, fim))
    pks.update(solicitacoes.values_list("municipio_id", flat=True))
    demandas = perm_demandas.queryset_visivel(usuario, DemandaEvento.objects.all()).filter(
        data_inicio_evento__isnull=False, municipio__isnull=False,
    ).filter(_sobrepoe("data_inicio_evento", "data_fim_evento", inicio, fim))
    pks.update(demandas.values_list("municipio_id", flat=True))
    return {int(p) for p in pks if p}


def models_q_roteiro_da_viagem(viagens):
    """Roteiros das viagens: ligados direto ou por um ofício delas."""
    from django.db.models import Q

    return Q(roteiro__viagem__in=viagens) | Q(roteiro__oficios__viagem__in=viagens)


def _feriados(usuario, inicio, fim) -> list[dict]:
    from core.feriados import feriados_no_periodo

    municipios = _municipios_do_periodo(usuario, inicio, fim)
    saida = []
    for f in feriados_no_periodo(inicio, fim - dt.timedelta(days=1), municipios):
        municipal = bool(f["municipio"])
        titulo = f["nome"] + (f" ({f['municipio']})" if municipal else "")
        saida.append({
            "id": f"feriado-{f['data'].isoformat()}-{titulo}",
            "title": titulo,
            "start": f["data"].isoformat(),
            "end": (f["data"] + dt.timedelta(days=1)).isoformat(),
            "allDay": True,
            # Faixa de fundo: não é clicável, não conta como compromisso.
            "display": "background",
            "classNames": ["ag-feriado", "ag-feriado--municipal" if municipal else "ag-feriado--geral"],
            "extendedProps": {
                "fonte": "feriado",
                "numero": 0,
                "fundo": True,
                "situacao": "",
                "situacao_slug": "",
                "url": "",
                "encerrado": False,
                "municipio": f["municipio"],
                "municipios": [f["municipio"]] if municipal else [],
                "tipo": "Feriado municipal" if municipal else "Feriado",
                "meu": False,
                "horario": "",
                "detalhes": [],
            },
        })
    return saida


FONTE = Fonte("feriado", "Feriados", _pode, _feriados)
