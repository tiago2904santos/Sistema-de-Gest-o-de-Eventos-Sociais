"""Choques de agenda no calendário (m130).

As telas de cada módulo perguntam a ``core.conflitos`` por um documento de
cada vez. A agenda precisa da pergunta inversa — de todos os compromissos do
mês, quais têm gente, viatura ou palestrante em dois lugares ao mesmo tempo —
e fazê-la documento a documento seria uma dúzia de consultas por viagem.

Aqui as ocupações do período são montadas de uma vez (ofícios, termos,
ordens de serviço, solicitações deferidas e palestras, com as mesmas regras
de ``core.conflitos``: cancelado não conta, encostar não é sobrepor, o que só
tem data ocupa o dia inteiro) e cruzadas em memória por recurso. O resultado
é indexado pela chave do compromisso na agenda (``("viagem", pk)``,
``("solicitacao", pk)``, ``("demanda", pk)``), que é o que ``marcar`` usa
para pôr ``ag-conflito`` nos eventos. O dossiê, que é um só, continua
perguntando a ``core.conflitos`` — ``secao_de_conflitos`` só desenha.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from django.urls import reverse

from core.conflitos import anotar_periodo_do_oficio, formatar_periodo, periodo_de_datas, sobrepoe

FONTES_COM_CONFLITO = ("viagem", "solicitacao", "demanda")


@dataclass(frozen=True)
class Ocupacao:
    """Um recurso ocupado por um documento num intervalo."""

    tipo: str  # servidor, viatura, unidade_movel, palestrante
    recurso_id: int
    recurso: str
    inicio: dt.datetime
    fim: dt.datetime
    chave: tuple  # a chave do compromisso na agenda: ("viagem", pk), ("solicitacao", pk), ("demanda", pk)
    documento: str  # "Ofício 12/2026", "Termo #3", "Solicitação #45"
    no_documento: str  # "no Ofício 12/2026"
    url: str
    local: str = ""
    papel: str = ""
    dia_inteiro: bool = False

    @property
    def periodo(self):
        return formatar_periodo(self.inicio, self.fim, dia_inteiro=self.dia_inteiro)

    def mensagem(self):
        local = f" ({self.local})" if self.local else ""
        return f"{self.recurso} também está {self.no_documento}{self.papel} {self.periodo}{local}"


def _equipe(oficios):
    pessoas, viaturas = set(), set()
    for o in oficios:
        if o.cancelado:
            continue
        pessoas.update(s.pk for s in o.servidores.all())
        if o.motorista_id:
            pessoas.add(o.motorista_id)
        if o.viatura_id:
            viaturas.add(o.viatura_id)
    return pessoas, viaturas


def _toca(campo_inicio, campo_fim, inicio, fim):
    from agenda.fontes import _sobrepoe

    return _sobrepoe(campo_inicio, campo_fim, inicio, fim)


def ocupacoes(inicio: dt.date, fim: dt.date) -> list[Ocupacao]:
    """Todas as ocupações que tocam [inicio, fim), de todas as fontes."""
    from demandas_eventos.models import DemandaEvento, StatusDemanda
    from solicitacoes.models import SolicitacaoEvento, StatusSolicitacao
    from viagens_oficios.models import Oficio
    from viagens_ordens.models import OrdemServico
    from viagens_termos.models import TermoAutorizacao

    comeco, termino = periodo_de_datas(inicio, fim - dt.timedelta(days=1))
    saida: list[Ocupacao] = []

    # Ofícios: equipe, motorista e viatura no período do roteiro, com horário.
    oficios = (
        anotar_periodo_do_oficio(Oficio.objects.filter(cancelado=False))
        .filter(_ini__lt=termino, _fim__gt=comeco)
        .select_related("viatura", "motorista", "viagem")
        .prefetch_related("servidores", "roteiro__destinos__municipio")
    )
    for o in oficios:
        documento = f"Ofício {o.numero_formatado}" if o.numero else f"Ofício (rascunho #{o.pk})"
        destinos = [d.municipio.nome for d in o.roteiro.destinos.all()] if o.roteiro_id else []
        base = dict(
            inicio=o._ini, fim=max(o._ini, o._fim), documento=documento, no_documento=f"no {documento}",
            chave=("viagem", o.viagem_id) if o.viagem_id else ("oficio", o.pk),
            url=reverse("viagens_oficios:editar", args=[o.pk]),
            local=", ".join(destinos) or (o.viagem.destino_display if o.viagem_id else ""),
        )
        vistos = set()
        for s in o.servidores.all():
            vistos.add(s.pk)
            saida.append(Ocupacao(tipo="servidor", recurso_id=s.pk, recurso=s.nome,
                                  papel=" como motorista" if s.pk == o.motorista_id else "", **base))
        if o.motorista_id and o.motorista_id not in vistos:
            saida.append(Ocupacao(tipo="servidor", recurso_id=o.motorista_id, recurso=o.motorista.nome, papel=" como motorista", **base))
        if o.viatura_id:
            saida.append(Ocupacao(tipo="viatura", recurso_id=o.viatura_id, recurso=f"Viatura {o.viatura.placa_formatada}", **base))

    # Termos com datas próprias: só o que acrescentam ao ofício vinculado.
    termos = (
        TermoAutorizacao.objects.filter(cancelado=False, data_evento_inicio__isnull=False)
        .filter(_toca("data_evento_inicio", "data_evento_fim", inicio, fim))
        .select_related("viatura", "oficio", "destino_cidade__estado")
        .prefetch_related("servidores", "oficio__servidores")
    )
    for t in termos:
        no_oficio, viaturas_do_oficio = _equipe([t.oficio] if t.oficio_id else [])
        viagem_id = t.viagem_id or (t.oficio.viagem_id if t.oficio_id else None)
        ini, fi = periodo_de_datas(t.data_evento_inicio, t.data_evento_fim)
        documento = f"Termo #{t.pk}"
        base = dict(
            inicio=ini, fim=fi, documento=documento, no_documento=f"no {documento}",
            chave=("viagem", viagem_id) if viagem_id else ("termo", t.pk),
            url=reverse("viagens_termos:editar", args=[t.pk]), local=t.destino_efetivo(), dia_inteiro=True,
        )
        for s in t.servidores.all():
            if s.pk not in no_oficio:
                saida.append(Ocupacao(tipo="servidor", recurso_id=s.pk, recurso=s.nome, **base))
        if t.viatura_id and t.viatura_id not in viaturas_do_oficio:
            saida.append(Ocupacao(tipo="viatura", recurso_id=t.viatura_id, recurso=f"Viatura {t.viatura.placa_formatada}", **base))

    # Ordens de serviço: a equipe, fora quem já está nos ofícios vinculados.
    ordens = (
        OrdemServico.objects.filter(cancelado=False, data_evento_inicio__isnull=False)
        .filter(_toca("data_evento_inicio", "data_evento_fim", inicio, fim))
        .prefetch_related("servidores", "oficios__servidores", "destinos__estado")
    )
    for o in ordens:
        no_oficio, _ = _equipe(o.oficios.all())
        ini, fi = periodo_de_datas(o.data_evento_inicio, o.data_evento_fim)
        base = dict(
            inicio=ini, fim=fi, documento=o.numero_formatado, no_documento=f"na {o.numero_formatado}",
            chave=("viagem", o.viagem_id) if o.viagem_id else ("ordem", o.pk),
            url=reverse("viagens_ordens:editar", args=[o.pk]),
            local=", ".join(f"{d.nome}/{d.estado.sigla}" for d in o.destinos.all()), dia_inteiro=True,
        )
        for s in o.servidores.all():
            if s.pk not in no_oficio:
                saida.append(Ocupacao(tipo="servidor", recurso_id=s.pk, recurso=s.nome, **base))

    # Solicitações deferidas: motorista e unidade móvel designados.
    solicitacoes = (
        SolicitacaoEvento.objects.filter(status__in=[StatusSolicitacao.DEFERIDA_EM_ANDAMENTO, StatusSolicitacao.ATENDIDA])
        .filter(_toca("data_inicio_evento", "data_fim_evento", inicio, fim))
        .exclude(motorista__isnull=True, unidade_movel_designada__isnull=True)
        .select_related("motorista", "unidade_movel_designada", "municipio")
    )
    for s in solicitacoes:
        ini, fi = periodo_de_datas(s.data_inicio_evento, s.data_fim_evento)
        base = dict(
            inicio=ini, fim=fi, documento=f"Solicitação #{s.pk}", no_documento=f"na Solicitação #{s.pk}",
            chave=("solicitacao", s.pk), url=reverse("solicitacoes:editar", args=[s.pk]),
            local=s.municipio.nome if s.municipio_id else "", dia_inteiro=True,
        )
        if s.motorista_id:
            saida.append(Ocupacao(tipo="servidor", recurso_id=s.motorista_id, recurso=s.motorista.nome, papel=" como motorista", **base))
        if s.unidade_movel_designada_id:
            saida.append(Ocupacao(tipo="unidade_movel", recurso_id=s.unidade_movel_designada_id,
                                  recurso=f"Unidade móvel {s.unidade_movel_designada.nome}", **base))

    # Palestras: o palestrante e, quando ligado ao cadastro, o servidor.
    demandas = (
        DemandaEvento.objects.exclude(status=StatusDemanda.CANCELADA)
        .filter(data_inicio_evento__isnull=False)
        .filter(_toca("data_inicio_evento", "data_fim_evento", inicio, fim))
        .select_related("municipio")
        .prefetch_related("palestrantes__servidor")
    )
    for d in demandas:
        ini, fi = periodo_de_datas(d.data_inicio_evento, d.data_fim_evento)
        rotulo = f"{d.get_evento_display()} #{d.pk}"
        base = dict(
            inicio=ini, fim=fi, documento=rotulo, no_documento=f"na {rotulo}", chave=("demanda", d.pk),
            url=reverse("demandas_eventos:editar", args=[d.pk]), local=d.municipio_display, dia_inteiro=True,
        )
        for p in d.palestrantes.all():
            saida.append(Ocupacao(tipo="palestrante", recurso_id=p.pk, recurso=p.nome, **base))
            if p.servidor_id:
                saida.append(Ocupacao(tipo="servidor", recurso_id=p.servidor_id, recurso=p.servidor.nome, papel=" como palestrante", **base))
    return saida


def conflitos_do_periodo(inicio: dt.date, fim: dt.date) -> dict[tuple, list[dict]]:
    """{chave do compromisso: [o que se sobrepõe a ele]} no período."""
    grupos: dict[tuple, list[Ocupacao]] = defaultdict(list)
    for o in ocupacoes(inicio, fim):
        grupos[(o.tipo, o.recurso_id)].append(o)
    achados: dict[tuple, dict[tuple, dict]] = defaultdict(dict)
    for lista in grupos.values():
        lista.sort(key=lambda o: o.inicio)
        for i, a in enumerate(lista):
            for b in lista[i + 1:]:
                if a.chave == b.chave or not sobrepoe(a.inicio, a.fim, b.inicio, b.fim):
                    continue
                achados[a.chave].setdefault((b.chave, b.tipo, b.recurso_id), _descrever(b))
                achados[b.chave].setdefault((a.chave, a.tipo, a.recurso_id), _descrever(a))
    return {chave: sorted(itens.values(), key=lambda c: (c["recurso"], c["documento"])) for chave, itens in achados.items()}


def _descrever(outro: Ocupacao) -> dict:
    return {
        "tipo": outro.tipo,
        "recurso": outro.recurso,
        "documento": outro.documento,
        "periodo": outro.periodo,
        "url": outro.url,
        "mensagem": outro.mensagem(),
    }


def marcar(eventos: list[dict], inicio: dt.date, fim: dt.date) -> list[dict]:
    """Põe ``ag-conflito`` e a lista de choques nos compromissos que os têm.

    Só as fontes com recursos (viagem, solicitação, palestra) e só o que está
    de pé: um compromisso cancelado não briga com ninguém.
    """
    alvos = [
        e for e in eventos
        if e["extendedProps"].get("fonte") in FONTES_COM_CONFLITO and not e["extendedProps"].get("encerrado")
    ]
    if not alvos:
        return eventos
    mapa = conflitos_do_periodo(inicio, fim)
    for e in alvos:
        p = e["extendedProps"]
        achados = mapa.get((p["fonte"], p["numero"]))
        if not achados:
            continue
        e["classNames"].append("ag-conflito")
        p["conflitos"] = [c["mensagem"] for c in achados]
        p["detalhes"].append(["Conflito de agenda", "; ".join(p["conflitos"])])
    return eventos


def secao_de_conflitos(achados) -> list[dict]:
    """A seção "Conflitos de agenda" do dossiê, a partir de ``core.conflitos``."""
    if not achados:
        return []
    return [{
        "titulo": "Conflitos de agenda",
        "campos": [],
        "linhas": [],
        "links": [{"texto": c.mensagem, "url": c.url} for c in achados],
    }]
