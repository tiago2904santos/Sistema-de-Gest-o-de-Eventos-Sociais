"""Conflitos de agenda: a mesma pessoa, viatura ou unidade móvel em dois lugares.

Um serviço só, usado por Solicitações (m011), Palestras, Ofícios (m049) e
Viagem (m067). Três regras valem para todos:

**Todas as unidades ao mesmo tempo.** A pergunta é "esse recurso está livre?",
e não "está livre na minha unidade?": nenhuma fonte filtra por unidade, setor
ou dono do registro.

**Horário, não só data.** Um recurso ocupa o intervalo [início, fim) do
compromisso, e só há conflito quando dois intervalos se sobrepõem de fato
(``início_a < fim_b e início_b < fim_a``). Quem chega a Curitiba em 12/10 às
17:30 pode sair para outro evento às 17:31 — e às 17:30 também, porque encostar
não é sobrepor. O que só tem data (solicitação, palestra) ocupa o dia inteiro:
de 00:00 do primeiro dia até 00:00 do dia seguinte ao último.

**Aviso, não bloqueio.** O serviço só descreve os conflitos; quem chama mostra
e deixa seguir. Cancelados não contam, e o registro em edição é excluído pela
``Consulta.excluir`` para não conflitar consigo mesmo.

Fontes registráveis
-------------------
Cada fonte é uma função ``(Consulta) -> Iterable[Conflito]`` registrada com
``@registrar_fonte("nome")``. Ela recebe os recursos procurados e o período e
devolve só o que se sobrepõe, consultando o banco pelas chaves dos recursos
(índices das FKs e das tabelas M2M) e pelo período — nunca varrendo a tabela
em Python. A extrajornada, quando existir, entra assim, no próprio app:

    from core.conflitos import Conflito, registrar_fonte

    @registrar_fonte("extrajornada")
    def _extrajornada(consulta):
        if not consulta.servidores:
            return []
        excluir = consulta.excluidos("extrajornada")
        escalas = (Extrajornada.objects.filter(cancelada=False, servidor_id__in=consulta.servidores,
                                               inicio__lt=consulta.fim, fim__gt=consulta.inicio)
                   .exclude(pk__in=excluir))
        return [Conflito(tipo="servidor", recurso=e.servidor.nome, no_documento=f"na Extrajornada #{e.pk}",
                         documento=f"Extrajornada #{e.pk}", inicio=e.inicio, fim=e.fim,
                         local=e.local, url=..., chave=("extrajornada", e.pk)) for e in escalas]

e é importada no ``ready()`` do app (como os sinais), para se registrar.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace

from django.db.models import DateTimeField, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

# ---------------------------------------------------------------------------
# Tipos


@dataclass(frozen=True)
class Consulta:
    """O que se procura: recursos, período e o que não conta.

    ``servidores`` são ``viagens_cadastros.Servidor`` — equipe e motorista são
    a mesma pessoa, então procurar um servidor acha as duas funções.
    ``municipios`` com ``pedido`` ("solicitacao" ou "demanda") procura pedido
    repetido: outro pedido para o mesmo município no mesmo período.
    ``excluir`` é ``{"oficio": {pk}, "solicitacao": {pk}, ...}``.
    """

    inicio: dt.datetime
    fim: dt.datetime
    servidores: frozenset = frozenset()
    viaturas: frozenset = frozenset()
    unidades_moveis: frozenset = frozenset()
    palestrantes: frozenset = frozenset()
    municipios: frozenset = frozenset()
    pedido: str = ""
    excluir: dict = field(default_factory=dict)

    def excluidos(self, fonte):
        return set(self.excluir.get(fonte) or ())

    @property
    def vazia(self):
        return not (
            self.servidores or self.viaturas or self.unidades_moveis
            or self.palestrantes or (self.municipios and self.pedido)
        )


@dataclass(frozen=True)
class Conflito:
    """Um compromisso que ocupa um dos recursos procurados no mesmo período."""

    tipo: str  # servidor, viatura, unidade_movel, palestrante, pedido
    recurso: str  # "FULANO", "Viatura ABC1D23", "Unidade Móvel 02"
    no_documento: str  # "no Ofício 12/2026", "na Solicitação #45"
    documento: str  # "Ofício 12/2026"
    inicio: dt.datetime
    fim: dt.datetime
    local: str = ""
    url: str = ""
    chave: tuple = ()
    papel: str = ""  # " como motorista"
    dia_inteiro: bool = False

    @property
    def periodo(self):
        return formatar_periodo(self.inicio, self.fim, dia_inteiro=self.dia_inteiro)

    @property
    def mensagem(self):
        local = f" ({self.local})" if self.local else ""
        if self.tipo == "pedido":
            return f"Já existe pedido {self.no_documento} para {self.local or 'o mesmo município'} {self.periodo}"
        return f"{self.recurso} já está {self.no_documento}{self.papel} {self.periodo}{local}"

    def como_dict(self):
        return {"tipo": self.tipo, "mensagem": self.mensagem, "url": self.url, "documento": self.documento}


# ---------------------------------------------------------------------------
# Período


def _aware(valor):
    if timezone.is_naive(valor):
        return timezone.make_aware(valor, timezone.get_current_timezone())
    return valor


def periodo_de_datas(inicio, fim=None, *, hora_inicio=None, hora_fim=None):
    """(início, fim) de um compromisso com data e, talvez, horário.

    Sem horário, o dia inteiro: do começo do primeiro dia ao começo do dia
    seguinte ao último. Devolve (None, None) sem data inicial.
    """
    if not inicio:
        return None, None
    fim = fim or inicio
    comeco = _aware(dt.datetime.combine(inicio, hora_inicio or dt.time.min))
    if hora_fim is not None:
        termino = _aware(dt.datetime.combine(fim, hora_fim))
    else:
        termino = _aware(dt.datetime.combine(fim + dt.timedelta(days=1), dt.time.min))
    return comeco, max(comeco, termino)


def sobrepoe(inicio_a, fim_a, inicio_b, fim_b):
    """Intervalos semiabertos que se sobrepõem de fato (encostar não conta)."""
    return inicio_a < fim_b and inicio_b < fim_a


def _local(valor):
    return timezone.localtime(valor) if timezone.is_aware(valor) else valor


def formatar_periodo(inicio, fim, *, dia_inteiro=False):
    inicio, fim = _local(inicio), _local(fim)
    if dia_inteiro:
        ultimo = (fim - dt.timedelta(microseconds=1)).date() if fim > inicio else inicio.date()
        if ultimo == inicio.date():
            return f"em {inicio:%d/%m/%Y}"
        return f"de {inicio:%d/%m} a {ultimo:%d/%m/%Y}"
    return f"de {inicio:%d/%m %H:%M} a {fim:%d/%m %H:%M}"


def _datas_locais(consulta):
    """O período da consulta em datas locais, para pré-filtrar campos de data."""
    fim = _local(consulta.fim)
    ultimo = (fim - dt.timedelta(microseconds=1)).date() if consulta.fim > consulta.inicio else fim.date()
    return _local(consulta.inicio).date(), ultimo


def _filtro_de_datas(consulta, campo_inicio="data_inicio_evento", campo_fim="data_fim_evento"):
    """Q dos registros só com datas que tocam o período (fim vazio = um dia)."""
    primeiro, ultimo = _datas_locais(consulta)
    return Q(**{f"{campo_inicio}__lte": ultimo}) & (
        Q(**{f"{campo_fim}__gte": primeiro})
        | Q(**{f"{campo_fim}__isnull": True, f"{campo_inicio}__gte": primeiro})
    )


# ---------------------------------------------------------------------------
# Registro das fontes

_FONTES: dict[str, Callable[[Consulta], Iterable[Conflito]]] = {}


def registrar_fonte(nome):
    """Registra uma fonte de compromissos (ver a documentação do módulo)."""

    def decorar(funcao):
        _FONTES[nome] = funcao
        return funcao

    return decorar


def fontes():
    return dict(_FONTES)


def conflitos(consulta: Consulta) -> list[Conflito]:
    """Todos os conflitos da consulta, em ordem de início, sem repetição."""
    if consulta is None or consulta.vazia or not (consulta.inicio and consulta.fim):
        return []
    vistos = set()
    achados = []
    for funcao in _FONTES.values():
        for conflito in funcao(consulta) or ():
            if not sobrepoe(consulta.inicio, consulta.fim, conflito.inicio, conflito.fim):
                continue
            chave = (conflito.chave, conflito.tipo, conflito.recurso)
            if chave in vistos:
                continue
            vistos.add(chave)
            achados.append(conflito)
    achados.sort(key=lambda c: (c.inicio, c.documento, c.recurso))
    return achados


def _ids(valores):
    return frozenset(int(v) for v in valores or () if v not in (None, "") and str(v).isdigit())


def consulta(inicio, fim, **kwargs):
    """Monta a Consulta limpando os ids (aceita instâncias, strings e None)."""
    if not (inicio and fim):
        return None
    limpos = {}
    for nome in ("servidores", "viaturas", "unidades_moveis", "palestrantes", "municipios"):
        valores = kwargs.pop(nome, ()) or ()
        limpos[nome] = _ids(getattr(v, "pk", v) for v in valores)
    return Consulta(inicio=_aware(inicio), fim=_aware(fim), **limpos, **kwargs)


# ---------------------------------------------------------------------------
# Atalhos por tela


def periodo_do_oficio(oficio):
    """(saída, chegada de volta) do ofício, pelo roteiro — com horário."""
    from viagens_oficios.roteiro_context import periodo_roteiro

    inicio, fim = periodo_roteiro(oficio.roteiro) if oficio.roteiro_id else (None, None)
    if inicio and not fim:
        fim = oficio.roteiro.chegada_dt or inicio
    if not (inicio and fim):
        return None, None
    return inicio, max(inicio, fim)


def consulta_do_oficio(oficio, *, servidores=None, viatura=None, motorista=None):
    """Recursos do ofício (ou os escolhidos na tela) no período do roteiro."""
    inicio, fim = periodo_do_oficio(oficio)
    if servidores is None:
        servidores = list(oficio.servidores.values_list("pk", flat=True)) if oficio.pk else []
        motorista = oficio.motorista_id
        viatura = oficio.viatura_id
    return consulta(
        inicio, fim,
        servidores=[*servidores, motorista],
        viaturas=[viatura],
        excluir={"oficio": {oficio.pk}},
    )


def conflitos_do_oficio(oficio, **kwargs):
    return conflitos(consulta_do_oficio(oficio, **kwargs))


def consulta_da_solicitacao(solicitacao):
    inicio, fim = periodo_de_datas(solicitacao.data_inicio_evento, solicitacao.data_fim_evento)
    return consulta(
        inicio, fim,
        servidores=[solicitacao.motorista_id],
        unidades_moveis=[solicitacao.unidade_movel_designada_id],
        municipios=[solicitacao.municipio_id],
        pedido="solicitacao",
        excluir={"solicitacao": {solicitacao.pk}},
    )


def conflitos_da_solicitacao(solicitacao):
    return conflitos(consulta_da_solicitacao(solicitacao))


def consulta_da_demanda(demanda, palestrantes=None):
    inicio, fim = periodo_de_datas(demanda.data_inicio_evento, demanda.data_fim_evento)
    if palestrantes is None:
        palestrantes = list(demanda.palestrantes.values_list("pk", flat=True)) if demanda.pk else []
    return consulta(
        inicio, fim,
        palestrantes=palestrantes,
        municipios=[demanda.municipio_id],
        pedido="demanda",
        excluir={"demanda": {demanda.pk}},
    )


def conflitos_da_demanda(demanda, palestrantes=None):
    return conflitos(consulta_da_demanda(demanda, palestrantes))


def conflitos_da_viagem(viagem):
    """Conflitos de cada ofício ativo da viagem, fora os da própria viagem."""
    proprios = set(viagem.oficios.values_list("pk", flat=True))
    achados, vistos = [], set()
    oficios = viagem.oficios.filter(cancelado=False).select_related("roteiro").prefetch_related("servidores")
    for oficio in oficios:
        base = consulta_do_oficio(
            oficio, servidores=[s.pk for s in oficio.servidores.all()],
            viatura=oficio.viatura_id, motorista=oficio.motorista_id,
        )
        if base is None:
            continue
        base = replace(base, excluir={"oficio": proprios})
        for conflito in conflitos(base):
            chave = (conflito.chave, conflito.tipo, conflito.recurso)
            if chave not in vistos:
                vistos.add(chave)
                achados.append(conflito)
    achados.sort(key=lambda c: (c.inicio, c.documento, c.recurso))
    return achados


# ---------------------------------------------------------------------------
# Fontes do sistema


@registrar_fonte("oficios")
def _oficios(consulta):
    """Ofícios de viagem não cancelados: equipe, motorista e viatura.

    O período é o do roteiro: saída da sede até a chegada de volta, com a
    mesma regra de ``periodo_roteiro`` (cabeçalho, senão os trechos) expressa
    no banco. O filtro por recurso vem primeiro, pelas FKs e pela tabela M2M.
    """
    if not (consulta.servidores or consulta.viaturas):
        return []
    from viagens_cadastros.models import Servidor
    from viagens_oficios.models import Oficio
    from viagens_roteiros.models import RoteiroTrecho
    from django.db.models import Prefetch

    trechos = RoteiroTrecho.objects.filter(roteiro=OuterRef("roteiro_id"))
    primeira_saida = trechos.exclude(saida_dt=None).order_by("saida_dt").values("saida_dt")[:1]
    ultima_chegada = trechos.exclude(chegada_dt=None).order_by("-chegada_dt").values("chegada_dt")[:1]
    por_recurso = Q(viatura_id__in=consulta.viaturas) | Q(motorista_id__in=consulta.servidores)
    if consulta.servidores:
        equipe = Oficio.servidores.through.objects.filter(servidor_id__in=consulta.servidores)
        por_recurso |= Q(pk__in=equipe.values("oficio_id"))
    oficios = (
        Oficio.objects.filter(cancelado=False)
        .filter(por_recurso)
        .exclude(pk__in=consulta.excluidos("oficio"))
        .annotate(
            _ini=Coalesce(F("roteiro__saida_dt"), Subquery(primeira_saida), output_field=DateTimeField()),
            _fim=Coalesce(
                F("roteiro__retorno_chegada_dt"), F("roteiro__retorno_saida_dt"),
                Subquery(ultima_chegada), F("roteiro__chegada_dt"), F("roteiro__saida_dt"),
                output_field=DateTimeField(),
            ),
        )
        .filter(_ini__lt=consulta.fim, _fim__gt=consulta.inicio)
        .select_related("viatura", "motorista", "viagem")
        .prefetch_related(
            Prefetch("servidores", queryset=Servidor.objects.filter(pk__in=consulta.servidores), to_attr="_equipe_procurada"),
            "roteiro__destinos__municipio",
        )
    )
    achados = []
    for oficio in oficios:
        documento = f"Ofício {oficio.numero_formatado}" if oficio.numero else f"Ofício (rascunho #{oficio.pk})"
        destinos = [d.municipio.nome for d in oficio.roteiro.destinos.all()] if oficio.roteiro_id else []
        local = ", ".join(destinos) or (oficio.viagem.destino_display if oficio.viagem_id else "")
        base = dict(
            no_documento=f"no {documento}", documento=documento, inicio=oficio._ini, fim=max(oficio._ini, oficio._fim),
            local=local, url=reverse("viagens_oficios:editar", args=[oficio.pk]), chave=("oficio", oficio.pk),
        )
        na_equipe = set()
        for servidor in oficio._equipe_procurada:
            na_equipe.add(servidor.pk)
            papel = " como motorista" if servidor.pk == oficio.motorista_id else ""
            achados.append(Conflito(tipo="servidor", recurso=servidor.nome, papel=papel, **base))
        if oficio.motorista_id in consulta.servidores and oficio.motorista_id not in na_equipe:
            achados.append(Conflito(tipo="servidor", recurso=oficio.motorista.nome, papel=" como motorista", **base))
        if oficio.viatura_id in consulta.viaturas:
            achados.append(Conflito(tipo="viatura", recurso=f"Viatura {oficio.viatura.placa_formatada}", **base))
    return achados


@registrar_fonte("solicitacoes")
def _solicitacoes(consulta):
    """Solicitações deferidas: unidade móvel e motorista designados no período
    do evento; e, nas Solicitações, pedido repetido (mesmo município e data)."""
    from solicitacoes.models import SolicitacaoEvento, StatusSolicitacao

    achados = []
    excluir = consulta.excluidos("solicitacao")
    datas = _filtro_de_datas(consulta)
    if consulta.unidades_moveis or consulta.servidores:
        deferidas = (
            SolicitacaoEvento.objects.filter(
                status__in=[StatusSolicitacao.DEFERIDA_EM_ANDAMENTO, StatusSolicitacao.ATENDIDA]
            )
            .filter(Q(unidade_movel_designada_id__in=consulta.unidades_moveis) | Q(motorista_id__in=consulta.servidores))
            .filter(datas)
            .exclude(pk__in=excluir)
            .select_related("unidade_movel_designada", "motorista", "municipio")
        )
        for s in deferidas:
            inicio, fim = periodo_de_datas(s.data_inicio_evento, s.data_fim_evento)
            base = dict(
                no_documento=f"na Solicitação #{s.pk}", documento=f"Solicitação #{s.pk}", inicio=inicio, fim=fim,
                local=s.municipio.nome if s.municipio_id else "", url=reverse("solicitacoes:editar", args=[s.pk]),
                chave=("solicitacao", s.pk), dia_inteiro=True,
            )
            if s.unidade_movel_designada_id in consulta.unidades_moveis:
                achados.append(Conflito(tipo="unidade_movel", recurso=f"Unidade móvel {s.unidade_movel_designada.nome}", **base))
            if s.motorista_id in consulta.servidores:
                achados.append(Conflito(tipo="servidor", recurso=s.motorista.nome, papel=" como motorista", **base))
    if consulta.pedido == "solicitacao" and consulta.municipios:
        repetidos = (
            SolicitacaoEvento.objects.filter(municipio_id__in=consulta.municipios)
            .exclude(status__in=[StatusSolicitacao.RASCUNHO, StatusSolicitacao.CANCELADA, StatusSolicitacao.NAO_ATENDIDA])
            .filter(datas)
            .exclude(pk__in=excluir)
            .select_related("municipio", "tipo_evento")
        )
        for s in repetidos:
            inicio, fim = periodo_de_datas(s.data_inicio_evento, s.data_fim_evento)
            tipo = f" ({s.tipo_evento.nome})" if s.tipo_evento_id else ""
            achados.append(Conflito(
                tipo="pedido", recurso="", no_documento=f"na Solicitação #{s.pk}{tipo}", documento=f"Solicitação #{s.pk}",
                inicio=inicio, fim=fim, local=s.municipio.nome, url=reverse("solicitacoes:editar", args=[s.pk]),
                chave=("solicitacao", s.pk), dia_inteiro=True,
            ))
    return achados


@registrar_fonte("palestras")
def _palestras(consulta):
    """Palestras e eventos da ASCOM não cancelados: palestrante na mesma data;
    e, nas Palestras, pedido repetido (mesmo município e data)."""
    from demandas_eventos.models import DemandaEvento, Palestrante, StatusDemanda
    from django.db.models import Prefetch

    achados = []
    excluir = consulta.excluidos("demanda")
    datas = _filtro_de_datas(consulta)
    ativas = DemandaEvento.objects.exclude(status=StatusDemanda.CANCELADA).exclude(pk__in=excluir).filter(datas)
    if consulta.palestrantes:
        through = DemandaEvento.palestrantes.through.objects.filter(palestrante_id__in=consulta.palestrantes)
        com_palestrante = (
            ativas.filter(pk__in=through.values("demandaevento_id"))
            .select_related("municipio")
            .prefetch_related(Prefetch(
                "palestrantes", queryset=Palestrante.objects.filter(pk__in=consulta.palestrantes), to_attr="_procurados",
            ))
        )
        for d in com_palestrante:
            inicio, fim = periodo_de_datas(d.data_inicio_evento, d.data_fim_evento)
            rotulo = f"{d.get_evento_display()} #{d.pk}"
            for p in d._procurados:
                achados.append(Conflito(
                    tipo="palestrante", recurso=p.nome, no_documento=f"na {rotulo}", documento=rotulo,
                    inicio=inicio, fim=fim, local=d.municipio_display,
                    url=reverse("demandas_eventos:editar", args=[d.pk]), chave=("demanda", d.pk), dia_inteiro=True,
                ))
    if consulta.pedido == "demanda" and consulta.municipios:
        for d in ativas.filter(municipio_id__in=consulta.municipios).select_related("municipio"):
            inicio, fim = periodo_de_datas(d.data_inicio_evento, d.data_fim_evento)
            rotulo = f"{d.get_evento_display()} #{d.pk}"
            achados.append(Conflito(
                tipo="pedido", recurso="", no_documento=f"na {rotulo}", documento=rotulo,
                inicio=inicio, fim=fim, local=d.municipio_display,
                url=reverse("demandas_eventos:editar", args=[d.pk]), chave=("demanda", d.pk), dia_inteiro=True,
            ))
    return achados


# ---------------------------------------------------------------------------
# Pedido HTTP (o endpoint JSON das telas)


def _data_ou_datahora(texto):
    texto = (texto or "").strip()
    if not texto:
        return None, False
    try:
        if "T" in texto or " " in texto:
            return dt.datetime.fromisoformat(texto.replace(" ", "T")), True
        return dt.date.fromisoformat(texto), False
    except ValueError:
        return None, False


def consulta_do_pedido(parametros):
    """A Consulta a partir dos parâmetros GET da tela.

    ``oficio=<pk>`` usa o período do roteiro do ofício e o exclui; senão,
    ``inicio``/``fim`` em data (dia inteiro) ou data e hora.
    """
    lista = parametros.getlist
    excluir = {}
    for fonte in ("oficio", "solicitacao", "demanda"):
        pks = _ids(lista(f"excluir_{fonte}"))
        if pks:
            excluir[fonte] = set(pks)
    inicio = fim = None
    oficio_pk = parametros.get("oficio", "")
    if oficio_pk.isdigit():
        from viagens_oficios.models import Oficio

        oficio = Oficio.objects.select_related("roteiro").filter(pk=int(oficio_pk)).first()
        if oficio is not None:
            inicio, fim = periodo_do_oficio(oficio)
            excluir.setdefault("oficio", set()).add(oficio.pk)
    else:
        valor_inicio, com_hora_inicio = _data_ou_datahora(parametros.get("inicio"))
        valor_fim, com_hora_fim = _data_ou_datahora(parametros.get("fim"))
        if isinstance(valor_inicio, dt.datetime):
            inicio = valor_inicio
            fim = valor_fim if isinstance(valor_fim, dt.datetime) else None
            if fim is None:
                fim = periodo_de_datas(valor_fim or valor_inicio.date())[1]
        elif valor_inicio:
            fim_data = valor_fim.date() if isinstance(valor_fim, dt.datetime) else valor_fim
            if fim_data and fim_data < valor_inicio:
                fim_data = None
            inicio, fim = periodo_de_datas(valor_inicio, fim_data)
    if not (inicio and fim) or fim < inicio:
        return None
    pedido = parametros.get("pedido", "")
    return consulta(
        inicio, fim,
        servidores=lista("servidores"),
        viaturas=lista("viaturas"),
        unidades_moveis=lista("unidades_moveis"),
        palestrantes=lista("palestrantes"),
        municipios=lista("municipios"),
        pedido=pedido if pedido in ("solicitacao", "demanda") else "",
        excluir=excluir,
    )
