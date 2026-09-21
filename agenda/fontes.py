"""As fontes da agenda: de onde vem cada compromisso, e quem pode vê-lo.

Nenhuma tela do sistema mostra viagens, eventos, coffee break e demandas
juntos — cada módulo tem a sua listagem, e quem quer saber o que acontece na
semana abre quatro. A agenda é o primeiro lugar onde a pergunta cabe inteira.

Cada fonte é uma função que recebe o usuário e o período e devolve
compromissos já no formato que o calendário consome. Duas regras valem para
todas, e são o motivo de este arquivo existir separado das views:

**A permissão é a de cada módulo, importada de lá.** Quem não enxerga Coffee
Break pelas telas não vê coffee break aqui — e nem fica sabendo que existe:
uma fonte fora do acesso simplesmente não entra na lista de filtros. Em
Solicitações e Demandas a regra é mais fina que "tem o módulo" (o dossiê é de
quem criou, a demanda é do setor), então a fonte passa pelo ``queryset_visivel``
das telas em vez de um filtro próprio. Regra de acesso copiada envelhece e
vira brecha.

**Datas de fim são exclusivas no calendário.** Uma viagem de 18 a 20 é
entregue como ``start=18, end=21``: é a convenção do FullCalendar, e errar
isso faz todo compromisso de vários dias aparecer um dia mais curto.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from django.db.models import Q
from django.urls import reverse


@dataclass(frozen=True)
class Fonte:
    slug: str
    rotulo: str
    pode: Callable  # usuario -> bool
    eventos: Callable  # (usuario, inicio, fim) -> list[dict]


def _fim_exclusivo(fim: dt.date) -> str:
    return (fim + dt.timedelta(days=1)).isoformat()


def _sobrepoe(campo_inicio: str, campo_fim: str, inicio: dt.date, fim: dt.date) -> Q:
    """Compromissos que tocam o período [inicio, fim).

    Fim em branco vale como "mesmo dia do início" — é como todos os módulos
    tratam um evento de um dia só.
    """
    return Q(**{f"{campo_inicio}__lt": fim}) & (
        Q(**{f"{campo_fim}__gte": inicio})
        | Q(**{f"{campo_fim}__isnull": True, f"{campo_inicio}__gte": inicio})
    )


def _evento(
    *,
    fonte: str,
    pk: int,
    titulo: str,
    inicio: dt.date,
    fim: dt.date | None,
    situacao: str,
    situacao_slug: str,
    url: str,
    detalhes: list[tuple[str, str]],
    encerrado: bool = False,
    municipio: str = "",
    tipo: str = "",
    meu: bool = False,
) -> dict:
    """Um compromisso no formato do calendário.

    ``encerrado`` marca o que já não vai acontecer (cancelado, não atendido):
    a tela esconde por padrão e deixa mostrar, em vez de misturar com o que
    está de pé.
    """
    slug = (situacao_slug or "").lower().replace(" ", "_")
    return {
        "id": f"{fonte}-{pk}",
        "title": titulo,
        "start": inicio.isoformat(),
        "end": _fim_exclusivo(fim or inicio),
        "allDay": True,
        "classNames": [f"ag-{fonte}", f"ag-sit-{slug}", "ag-encerrado" if encerrado else "ag-ativo"],
        "extendedProps": {
            "fonte": fonte,
            "numero": pk,
            "situacao": situacao,
            "situacao_slug": slug,
            "url": url,
            "encerrado": encerrado,
            # Para os filtros locais da tela; a agenda monta as opções a
            # partir do que veio, com contagem.
            "municipio": municipio,
            "tipo": tipo,
            "meu": meu,
            "detalhes": [[rotulo, valor] for rotulo, valor in detalhes if valor],
        },
    }


# ---------------------------------------------------------------------------
# Viagens
# ---------------------------------------------------------------------------


def _pode_viagens(usuario) -> bool:
    from viagens_cadastros.permissions import pode_acessar

    return pode_acessar(usuario)


def _viagens(usuario, inicio, fim) -> list[dict]:
    from viagens_viagem.models import Viagem

    consulta = (
        Viagem.objects.filter(_sobrepoe("data_inicio", "data_fim", inicio, fim))
        .select_related("destino_municipio__estado", "destino_estado", "unidade_responsavel")
        .order_by("data_inicio", "id")
    )
    saida = []
    for v in consulta:
        motivo = (v.motivo or "").strip()
        saida.append(
            _evento(
                fonte="viagem",
                pk=v.pk,
                titulo=v.destino_display + (f" — {motivo}" if motivo else ""),
                inicio=v.data_inicio,
                fim=v.data_fim,
                situacao=v.get_status_display(),
                situacao_slug=v.status,
                url=reverse("viagens_viagem:painel", args=[v.pk]),
                encerrado=bool(v.cancelado),
                municipio=v.destino_display,
                tipo=str(v.unidade_responsavel) if v.unidade_responsavel_id else "",
                detalhes=[
                    ("Destino", v.destino_display),
                    ("Período", v.periodo_display),
                    ("Motivo", motivo),
                    ("Unidade", str(v.unidade_responsavel) if v.unidade_responsavel_id else ""),
                    ("Cancelada", v.motivo_cancelamento if v.cancelado else ""),
                ],
            )
        )
    return saida


# ---------------------------------------------------------------------------
# Solicitações de evento
# ---------------------------------------------------------------------------


def _pode_solicitacoes(usuario) -> bool:
    # Núcleo do sistema: exige login, não módulo. O recorte fino (o dossiê é
    # de quem criou) acontece no queryset.
    return bool(usuario and usuario.is_authenticated)


def _solicitacoes(usuario, inicio, fim) -> list[dict]:
    from solicitacoes import permissions
    from solicitacoes.models import SolicitacaoEvento, StatusSolicitacao

    consulta = (
        permissions.queryset_visivel(usuario, SolicitacaoEvento.objects.all())
        .filter(data_inicio_evento__isnull=False)
        .filter(_sobrepoe("data_inicio_evento", "data_fim_evento", inicio, fim))
        .select_related("municipio", "tipo_evento")
        .order_by("data_inicio_evento", "id")
    )
    encerrados = {StatusSolicitacao.CANCELADA, StatusSolicitacao.NAO_ATENDIDA}
    saida = []
    for s in consulta:
        lugar = str(s.municipio) if s.municipio_id else "Sem município"
        tipo = str(s.tipo_evento) if s.tipo_evento_id else ""
        saida.append(
            _evento(
                fonte="solicitacao",
                pk=s.pk,
                titulo=lugar + (f" — {tipo}" if tipo else ""),
                inicio=s.data_inicio_evento,
                fim=s.data_fim_evento,
                situacao=s.get_status_display(),
                situacao_slug=s.status,
                url=reverse("solicitacoes:editar", args=[s.pk]),
                encerrado=s.status in encerrados,
                municipio=lugar,
                tipo=tipo,
                meu=s.criado_por_id == getattr(usuario, "pk", None),
                detalhes=[
                    ("Município", lugar),
                    ("Tipo de evento", tipo),
                    ("Local", s.local_evento),
                    ("Solicitante", s.solicitante_nome),
                    ("Servidores previstos", str(s.quantidade_servidores or "")),
                    ("Decisão da DG", s.get_decisao_dg_display() if s.decisao_dg else ""),
                ],
            )
        )
    return saida


# ---------------------------------------------------------------------------
# Coffee break
# ---------------------------------------------------------------------------


def _pode_coffee(usuario) -> bool:
    from coffee_break.permissions import pode_acessar

    return pode_acessar(usuario)


def _coffee(usuario, inicio, fim) -> list[dict]:
    from coffee_break.models import SolicitacaoCoffeeBreak

    consulta = (
        SolicitacaoCoffeeBreak.objects.filter(data_inicio_evento__isnull=False)
        .filter(_sobrepoe("data_inicio_evento", "data_fim_evento", inicio, fim))
        .select_related("lote")
        .order_by("data_inicio_evento", "id")
    )
    saida = []
    for c in consulta:
        descricao = (c.descricao_evento or "").strip()
        quantidade = c.quantidade or 0
        saida.append(
            _evento(
                fonte="coffee",
                pk=c.pk,
                titulo=(descricao[:70] if descricao else "Coffee break") + f" ({quantidade})",
                inicio=c.data_inicio_evento,
                fim=c.data_fim_evento,
                situacao="Cancelada" if c.cancelada else "Ativa",
                situacao_slug="cancelada" if c.cancelada else "ativa",
                url=reverse("coffee_break:editar", args=[c.pk]),
                encerrado=bool(c.cancelada),
                tipo="Coffee break",
                meu=c.criado_por_id == getattr(usuario, "pk", None),
                detalhes=[
                    ("Evento", descricao),
                    ("Quantidade", f"{quantidade} unidade(s)"),
                    ("Número", c.numero or ""),
                    ("Lote", str(c.lote) if c.lote_id else ""),
                    ("Cancelada", c.motivo_cancelamento if c.cancelada else ""),
                ],
            )
        )
    return saida


# ---------------------------------------------------------------------------
# Demandas da ASCOM
# ---------------------------------------------------------------------------


def _pode_demandas(usuario) -> bool:
    from accounts.modulos import usuario_tem_modulo
    from demandas_eventos.permissions import CODIGO_MODULO

    return usuario_tem_modulo(usuario, CODIGO_MODULO)


def _demandas(usuario, inicio, fim) -> list[dict]:
    from demandas_eventos import permissions
    from demandas_eventos.models import DemandaEvento, StatusDemanda

    consulta = (
        permissions.queryset_visivel(usuario, DemandaEvento.objects.all())
        .filter(data_inicio_evento__isnull=False)
        .filter(_sobrepoe("data_inicio_evento", "data_fim_evento", inicio, fim))
        .select_related("municipio", "tema", "tipo_evento")
        .order_by("data_inicio_evento", "id")
    )
    encerrados = {StatusDemanda.CANCELADA, StatusDemanda.NAO_ATENDER}
    saida = []
    for d in consulta:
        lugar = str(d.municipio) if d.municipio_id else (d.municipio_texto or "Sem município")
        tema = str(d.tema) if d.tema_id else ""
        saida.append(
            _evento(
                fonte="demanda",
                pk=d.pk,
                titulo=lugar + (f" — {tema}" if tema else ""),
                inicio=d.data_inicio_evento,
                fim=d.data_fim_evento,
                situacao=d.get_status_display(),
                situacao_slug=d.status,
                url=reverse("demandas_eventos:editar", args=[d.pk]),
                encerrado=d.status in encerrados,
                municipio=lugar,
                tipo=tema,
                meu=d.criado_por_id == getattr(usuario, "pk", None),
                detalhes=[
                    ("Município", lugar),
                    ("Tema", tema),
                    ("Tipo de evento", str(d.tipo_evento) if d.tipo_evento_id else ""),
                    ("Solicitante", d.solicitante),
                    ("Público previsto", str(d.quantidade_publico or "")),
                ],
            )
        )
    return saida


# A ordem é a ordem dos filtros na tela. Viagens primeiro porque é o módulo
# de referência do sistema, e o que mais gera deslocamento de verdade.
FONTES: tuple[Fonte, ...] = (
    Fonte("viagem", "Viagens", _pode_viagens, _viagens),
    Fonte("solicitacao", "Solicitações de evento", _pode_solicitacoes, _solicitacoes),
    Fonte("coffee", "Coffee break", _pode_coffee, _coffee),
    Fonte("demanda", "Demandas da ASCOM", _pode_demandas, _demandas),
)


def fontes_de(usuario) -> list[Fonte]:
    """As fontes que esta pessoa pode ver — o que a tela lista como filtro."""
    return [f for f in FONTES if f.pode(usuario)]


def eventos_de(usuario, inicio: dt.date, fim: dt.date, slugs=None) -> list[dict]:
    """Todos os compromissos do período, só das fontes que a pessoa pode ver.

    ``slugs`` restringe às fontes pedidas; uma fonte pedida fora do acesso é
    ignorada em silêncio — pedir pelo nome não é o que abre a porta.
    """
    pedidas = set(slugs or ())
    saida = []
    for fonte in fontes_de(usuario):
        if pedidas and fonte.slug not in pedidas:
            continue
        saida.extend(fonte.eventos(usuario, inicio, fim))
    return saida
