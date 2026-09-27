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


#: Quanto dura um compromisso que só tem hora de início (palestra, pauta).
DURACAO_PADRAO = dt.timedelta(hours=2)


def _horario_texto(hora_inicio, hora_fim) -> str:
    if not hora_inicio:
        return ""
    return f"{hora_inicio:%H:%M}" + (f"–{hora_fim:%H:%M}" if hora_fim else "")


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
    municipios: list[str] | None = None,
    tipo: str = "",
    meu: bool = False,
    chave: str = "",
    hora_inicio: dt.time | None = None,
    hora_fim: dt.time | None = None,
) -> dict:
    """Um compromisso no formato do calendário.

    ``encerrado`` marca o que já não vai acontecer (cancelado, não atendido):
    a tela esconde por padrão e deixa mostrar, em vez de misturar com o que
    está de pé.

    ``pk`` é o que abre o dossiê (``agenda:detalhe``); ``chave`` distingue o
    evento quando vários apontam para o mesmo dossiê (os termos aditivos de um
    contrato, as certidões de um fornecedor).

    **Horário (m132).** Com ``hora_inicio`` e um dia só, o compromisso entra
    com hora (``allDay=False``) e ocupa a grade das visões Semana e Dia; sem
    hora de fim, dura ``DURACAO_PADRAO``. O que atravessa dias continua
    como dia inteiro, com o horário no título — uma viagem de três dias não
    é uma faixa das 6h de segunda às 22h de quarta.

    ``municipios`` lista todos os lugares por onde o compromisso passa: é o
    que o filtro de município da tela consulta; ``municipio`` é o principal.
    """
    slug = (situacao_slug or "").lower().replace(" ", "_")
    lugares = [m for m in (municipios or []) if m]
    if municipio and municipio not in lugares:
        lugares.insert(0, municipio)
    horario = _horario_texto(hora_inicio, hora_fim)
    um_dia = not fim or fim == inicio
    if hora_inicio and um_dia:
        comeco = dt.datetime.combine(inicio, hora_inicio)
        termino = dt.datetime.combine(inicio, hora_fim) if hora_fim else None
        if termino is None or termino <= comeco:
            termino = comeco + DURACAO_PADRAO
        start, end, dia_inteiro = comeco.isoformat(timespec="minutes"), termino.isoformat(timespec="minutes"), False
    else:
        start, end, dia_inteiro = inicio.isoformat(), _fim_exclusivo(fim or inicio), True
        if horario:
            titulo = f"{titulo} · {horario}"
    return {
        "id": f"{fonte}-{chave or pk}",
        "title": titulo,
        "start": start,
        "end": end,
        "allDay": dia_inteiro,
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
            "municipio": municipio or (lugares[0] if lugares else ""),
            "municipios": lugares,
            "tipo": tipo,
            "meu": meu,
            "horario": horario,
            "detalhes": [[rotulo, valor] for rotulo, valor in detalhes if valor],
        },
    }


# ---------------------------------------------------------------------------
# Viagens
# ---------------------------------------------------------------------------


def _pode_viagens(usuario) -> bool:
    from viagens_cadastros.permissions import pode_acessar

    return pode_acessar(usuario)


def _municipios_extras(viagens) -> dict[int, str]:
    """{pk: "Cidade/UF"} dos destinos adicionais de todas as viagens, numa consulta."""
    from cadastros.models import Municipio

    pks = {
        municipio_id
        for v in viagens
        for _estado_id, municipio_id in v.destinos_pares()[1:]
        if municipio_id
    }
    if not pks:
        return {}
    return {m.pk: f"{m.nome}/{m.estado.sigla}" for m in Municipio.objects.filter(pk__in=pks).select_related("estado")}


def _destinos_da_viagem(v, extras: dict[int, str]) -> list[str]:
    """O destino principal e os adicionais, sem repetir."""
    destinos = [v.destino_display]
    for _estado_id, municipio_id in v.destinos_pares()[1:]:
        nome = extras.get(municipio_id)
        if nome and nome not in destinos:
            destinos.append(nome)
    return destinos


def _roteiros_da_viagem(v):
    candidatos = list(v.roteiros.all())
    for oficio in v.oficios.all():
        if oficio.roteiro_id and oficio.roteiro:
            candidatos.append(oficio.roteiro)
    return {r.pk: r for r in candidatos if not r.cancelado}.values()


def _destinos_dos_roteiros(v) -> list[str]:
    """Os municípios dos roteiros (trecho a trecho): a busca por cidade acha a viagem que passa por ela."""
    nomes = []
    for r in _roteiros_da_viagem(v):
        for d in r.destinos.all():
            nome = f"{d.municipio.nome}/{d.municipio.estado.sigla}"
            if nome not in nomes:
                nomes.append(nome)
    return nomes


def _horario_da_viagem(v):
    """(hora da saída, hora da chegada de volta) do roteiro mais cedo; senão, os da viagem."""
    from django.utils import timezone

    com_saida = [r for r in _roteiros_da_viagem(v) if r.saida_dt]
    if com_saida:
        r = min(com_saida, key=lambda r: r.saida_dt)
        volta = r.retorno_chegada_dt or r.chegada_dt
        return timezone.localtime(r.saida_dt).time(), timezone.localtime(volta).time() if volta else None
    return v.horario_inicio, v.horario_fim


def _viagens(usuario, inicio, fim) -> list[dict]:
    from viagens_viagem.models import Viagem

    from .situacao import consulta_de_viagens, situacao_da_viagem

    consulta = consulta_de_viagens(
        Viagem.objects.filter(_sobrepoe("data_inicio", "data_fim", inicio, fim))
        .select_related("destino_municipio__estado", "destino_estado", "unidade_responsavel")
        .prefetch_related("roteiros__destinos__municipio__estado", "oficios__roteiro__destinos__municipio__estado")
        .order_by("data_inicio", "id")
    )
    viagens = list(consulta)
    extras = _municipios_extras(viagens)
    saida = []
    for v in viagens:
        motivo = (v.motivo or "").strip()
        # A situação real, como na lista de Viagens (m131) — não o campo status.
        situacao, situacao_slug, _tom = situacao_da_viagem(v)
        # Todos os destinos (m132): os da viagem no título, os dos roteiros no filtro.
        destinos = _destinos_da_viagem(v, extras)
        hora_inicio, hora_fim = _horario_da_viagem(v)
        saida.append(
            _evento(
                fonte="viagem",
                pk=v.pk,
                titulo=", ".join(destinos) + (f" — {motivo}" if motivo else ""),
                inicio=v.data_inicio,
                fim=v.data_fim,
                situacao=situacao,
                situacao_slug=situacao_slug,
                url=reverse("viagens_viagem:painel", args=[v.pk]),
                encerrado=bool(v.cancelado),
                municipio=v.destino_display,
                municipios=destinos + _destinos_dos_roteiros(v),
                tipo=str(v.unidade_responsavel) if v.unidade_responsavel_id else "",
                hora_inicio=hora_inicio,
                hora_fim=hora_fim,
                detalhes=[
                    ("Destino", ", ".join(destinos)),
                    ("Período", v.periodo_display),
                    ("Horário", _horario_texto(hora_inicio, hora_fim)),
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
# Palestras e eventos da ASCOM
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
        .select_related("municipio").prefetch_related("temas", "palestrantes")
        .order_by("data_inicio_evento", "id")
    )
    encerrados = {StatusDemanda.CANCELADA}
    saida = []
    for d in consulta:
        lugar = str(d.municipio) if d.municipio_id else (d.municipio_texto or "Sem município")
        tema = d.temas_display
        saida.append(
            _evento(
                fonte="demanda",
                pk=d.pk,
                titulo=f"{d.get_evento_display()} · {lugar}" + (f" — {tema}" if tema else ""),
                inicio=d.data_inicio_evento,
                fim=d.data_fim_evento,
                situacao=d.get_status_display(),
                situacao_slug=d.status,
                url=reverse("demandas_eventos:editar", args=[d.pk]),
                encerrado=d.status in encerrados,
                municipio=lugar,
                tipo=d.get_evento_display(),
                meu=d.criado_por_id == getattr(usuario, "pk", None),
                # A palestra tem hora de início, não de fim: dura DURACAO_PADRAO (m132).
                hora_inicio=d.hora_inicio,
                detalhes=[
                    ("Município", lugar),
                    ("Evento", d.get_evento_display()),
                    ("Tema", tema),
                    ("Horário", d.horario_display),
                    ("Servidor", d.servidores_display),
                    ("Solicitante", d.solicitante),
                    ("Quantidade de público", str(d.quantidade_publico or "")),
                ],
            )
        )
    return saida


# A ordem é a ordem dos filtros na tela. Viagens primeiro porque é o módulo
# de referência do sistema, e o que mais gera deslocamento de verdade.
def _fontes_de_prazos() -> tuple[Fonte, ...]:
    # Importados aqui porque usam ``_evento`` e ``Fonte`` deste módulo: a
    # camada de prazos (m129) e os feriados (m138) entram depois dos
    # compromissos.
    from .feriados import FONTE as FERIADOS
    from .prazos import FONTES as PRAZOS

    return (*PRAZOS, FERIADOS)


FONTES: tuple[Fonte, ...] = (
    Fonte("viagem", "Viagens", _pode_viagens, _viagens),
    Fonte("solicitacao", "Solicitações de evento", _pode_solicitacoes, _solicitacoes),
    Fonte("coffee", "Coffee break", _pode_coffee, _coffee),
    Fonte("demanda", "Palestras e eventos", _pode_demandas, _demandas),
    *_fontes_de_prazos(),
)


def fontes_de(usuario) -> list[Fonte]:
    """As fontes que esta pessoa pode ver — o que a tela lista como filtro."""
    return [f for f in FONTES if f.pode(usuario)]


def eventos_de(usuario, inicio: dt.date, fim: dt.date, slugs=None) -> list[dict]:
    """Todos os compromissos do período, só das fontes que a pessoa pode ver.

    ``slugs`` restringe às fontes pedidas; uma fonte pedida fora do acesso é
    ignorada em silêncio — pedir pelo nome não é o que abre a porta.
    """
    from .conflitos import marcar

    pedidas = set(slugs or ())
    saida = []
    for fonte in fontes_de(usuario):
        if pedidas and fonte.slug not in pedidas:
            continue
        saida.extend(fonte.eventos(usuario, inicio, fim))
    # Choques de agenda (m130): a mesma pessoa, viatura ou palestrante em dois
    # compromissos ao mesmo tempo ganha ag-conflito.
    return marcar(saida, inicio, fim)
