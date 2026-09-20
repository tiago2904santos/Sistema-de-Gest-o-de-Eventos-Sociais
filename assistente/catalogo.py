"""As ferramentas concretas: o que o assistente sabe consultar e preparar.

Cada função aqui é fina de propósito — monta um filtro, chama o ORM pelos
mesmos caminhos das telas e devolve um ``Resultado`` já legível. A regra de
negócio continua morando nos ``services.py`` de cada módulo; se ela mudar lá,
muda aqui junto, sem ninguém precisar lembrar.

O acesso segue o módulo ``VIAGENS``: quem não enxerga o módulo pelas telas
também não o enxerga pelo assistente. É a mesma função de permissão, não uma
cópia — cópia de regra de acesso envelhece e vira brecha.
"""

from __future__ import annotations

import datetime as dt

from django.db.models import DateField, Q
from django.db.models.functions import Coalesce, TruncDate

from .ferramentas import Parametro, Resultado, registrar
from .permissions import pode_consultar_viagens as pode_ver_viagens
from .permissions import pode_preparar_documentos
from .resolucao import NENHUM, descrever, resolver_municipio

# Sem período dito, a consulta olha daqui para a frente por este tanto de dias:
# "quem vai para Maringá" quase sempre quer dizer "vai", não "foi".
JANELA_PADRAO_DIAS = 90

# Uma resposta de WhatsApp não pode ser uma listagem inteira; acima disso ela
# diz o total e manda abrir no sistema.
LIMITE_LINHAS = 20


def _data_de_referencia(queryset):
    """A data que vale para um ofício, na ordem em que a viagem a define.

    O mesmo deslocamento tem data em três lugares — na viagem que o agrupa, no
    roteiro que o detalha e, na falta dos dois, na criação do ofício. Coalesce
    escolhe a primeira preenchida para que o filtro por período funcione tanto
    para o que já está montado quanto para o que ainda é rascunho.
    """
    return queryset.annotate(
        data_ref=Coalesce(
            "viagem__data_inicio",
            TruncDate("roteiro__saida_dt"),
            "data_criacao",
            # Explícito porque o PostgreSQL recusa COALESCE sem tipo comum
            # decidido; o SQLite aceitaria a inferência e o erro só apareceria
            # em produção.
            output_field=DateField(),
        )
    )


def _janela(inicio, fim):
    hoje = dt.date.today()
    if inicio and fim:
        return inicio, fim
    if inicio:
        return inicio, inicio + dt.timedelta(days=JANELA_PADRAO_DIAS)
    if fim:
        return hoje, fim
    return hoje, hoje + dt.timedelta(days=JANELA_PADRAO_DIAS)


def _periodo_por_extenso(inicio, fim):
    if inicio == fim:
        return f"em {inicio.strftime('%d/%m/%Y')}"
    return f"de {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"


@registrar(
    "consultar_deslocamentos",
    descricao=(
        "Quem vai (ou foi) a um destino em um período: servidores, motorista e "
        "viatura de cada ofício de viagem."
    ),
    parametros=(
        Parametro("destino", "texto", "Município de destino", obrigatorio=True),
        Parametro("inicio", "data", "Primeiro dia do período"),
        Parametro("fim", "data", "Último dia do período"),
    ),
    permissao=pode_ver_viagens,
)
def consultar_deslocamentos(usuario, destino, inicio=None, fim=None):
    from viagens_oficios.models import Oficio

    municipio = resolver_municipio(destino)
    if municipio.status == NENHUM:
        return Resultado(
            titulo=f"Não encontrei o município “{destino}” no cadastro.",
            dados={"erro": "municipio_desconhecido", "termo": destino},
        )
    if not municipio.resolvido:
        return Resultado(
            titulo=f"“{destino}” pode ser mais de um município.",
            linhas=[f"• {descrever(c)}" for c in municipio.candidatos],
            dados={"erro": "municipio_ambiguo", "candidatos": [c.pk for c in municipio.candidatos]},
        )

    alvo = municipio.escolhido
    inicio, fim = _janela(inicio, fim)
    # O destino aparece na viagem (destino principal), no roteiro (lista de
    # destinos) ou no trecho calculado; um ofício pode ter só um dos três.
    no_destino = (
        Q(viagem__destino_municipio=alvo)
        | Q(roteiro__destinos__municipio=alvo)
        | Q(roteiro__trechos__destino_municipio=alvo)
    )
    oficios = (
        _data_de_referencia(Oficio.objects.filter(cancelado=False))
        .filter(no_destino, data_ref__gte=inicio, data_ref__lte=fim)
        .select_related("viagem", "motorista", "viatura", "roteiro")
        .prefetch_related("servidores")
        .distinct()
        .order_by("data_ref", "pk")
    )

    pessoas: dict[int, dict] = {}
    for oficio in oficios:
        equipe = list(oficio.servidores.all())
        if oficio.motorista and oficio.motorista not in equipe:
            equipe.append(oficio.motorista)
        for servidor in equipe:
            registro = pessoas.setdefault(
                servidor.pk,
                {"nome": servidor.nome, "papeis": set(), "datas": set(), "oficios": set()},
            )
            registro["papeis"].add(
                "motorista" if servidor.pk == oficio.motorista_id else "servidor"
            )
            if oficio.data_ref:
                registro["datas"].add(oficio.data_ref)
            registro["oficios"].add(oficio.pk)

    rotulo = f"{alvo.nome}/{alvo.estado.sigla}"
    if not pessoas:
        return Resultado(
            titulo=f"Ninguém escalado para {rotulo} {_periodo_por_extenso(inicio, fim)}.",
            dados={"municipio": alvo.pk, "total": 0},
        )

    ordenadas = sorted(pessoas.values(), key=lambda p: (min(p["datas"]) if p["datas"] else dt.date.max, p["nome"]))
    linhas = []
    for pessoa in ordenadas[:LIMITE_LINHAS]:
        datas = ", ".join(d.strftime("%d/%m") for d in sorted(pessoa["datas"]))
        papel = " (motorista)" if "motorista" in pessoa["papeis"] else ""
        linhas.append(f"• {pessoa['nome']}{papel} — {datas}" if datas else f"• {pessoa['nome']}{papel}")
    if len(ordenadas) > LIMITE_LINHAS:
        linhas.append(f"… e mais {len(ordenadas) - LIMITE_LINHAS}. Abra a lista no sistema para ver todos.")

    return Resultado(
        titulo=(
            f"{len(ordenadas)} servidor(es) para {rotulo} "
            f"{_periodo_por_extenso(inicio, fim)}:"
        ),
        linhas=linhas,
        dados={
            "municipio": alvo.pk,
            "total": len(ordenadas),
            "servidores": [p["nome"] for p in ordenadas],
        },
    )


@registrar(
    "consultar_viagens",
    descricao="Viagens de um período, com destino, situação e responsável.",
    parametros=(
        Parametro("inicio", "data", "Primeiro dia do período"),
        Parametro("fim", "data", "Último dia do período"),
        Parametro("destino", "texto", "Município de destino, se houver"),
    ),
    permissao=pode_ver_viagens,
)
def consultar_viagens(usuario, inicio=None, fim=None, destino=None):
    from viagens_viagem.models import Viagem

    inicio, fim = _janela(inicio, fim)
    viagens = Viagem.objects.filter(cancelado=False).select_related(
        "destino_municipio__estado", "destino_estado", "responsavel"
    )
    # Uma viagem entra no período se qualquer parte dela cai dentro dele.
    viagens = viagens.filter(
        Q(data_inicio__lte=fim, data_fim__gte=inicio)
        | Q(data_inicio__range=(inicio, fim), data_fim__isnull=True)
    )
    if destino:
        municipio = resolver_municipio(destino)
        if not municipio.resolvido:
            return Resultado(
                titulo=f"Não consegui identificar o destino “{destino}”.",
                dados={"erro": "municipio_ambiguo" if municipio.candidatos else "municipio_desconhecido"},
            )
        viagens = viagens.filter(destino_municipio=municipio.escolhido)

    viagens = viagens.order_by("data_inicio", "pk")
    total = viagens.count()
    if not total:
        return Resultado(
            titulo=f"Nenhuma viagem {_periodo_por_extenso(inicio, fim)}.",
            dados={"total": 0},
        )
    linhas = [
        f"• #{v.pk} {v.destino_display} — {v.periodo_display} — {v.get_status_display()}"
        for v in viagens[:LIMITE_LINHAS]
    ]
    if total > LIMITE_LINHAS:
        linhas.append(f"… e mais {total - LIMITE_LINHAS}.")
    return Resultado(
        titulo=f"{total} viagem(ns) {_periodo_por_extenso(inicio, fim)}:",
        linhas=linhas,
        dados={"total": total, "ids": [v.pk for v in viagens[:LIMITE_LINHAS]]},
    )


@registrar(
    "consultar_pendencias",
    descricao=(
        "O que está parado: diários de bordo sem KM, prestações não iniciadas, "
        "ofícios em rascunho e viagens próximas sem termo de autorização."
    ),
    permissao=pode_ver_viagens,
)
def consultar_pendencias(usuario):
    from viagens_oficios.models import Oficio
    from viagens_prestacoes.models import DiarioBordoTrecho, PrestacaoServidor
    from viagens_viagem.models import Viagem

    hoje = dt.date.today()

    sem_km = (
        DiarioBordoTrecho.objects.filter(
            Q(km_inicial__isnull=True) | Q(km_final__isnull=True)
        )
        .select_related("diario__prestacao__oficio")
        .order_by("diario_id", "ordem")
    )
    prestacoes_sem_km = sorted(
        {t.diario.prestacao.oficio.numero_formatado for t in sem_km if t.diario_id}
    )

    nao_iniciadas = (
        PrestacaoServidor.objects.filter(
            status=PrestacaoServidor.STATUS_PENDENTE, arquivada=False, finalizada=False
        )
        .select_related("servidor")
        .order_by("servidor__nome")
    )

    rascunhos = Oficio.objects.filter(
        cancelado=False, status=Oficio.STATUS_RASCUNHO
    ).order_by("-data_criacao")

    # "Sem termo" só é pendência para o que está prestes a acontecer; viagem
    # longe ainda tem tempo de ser montada.
    sem_termo = Viagem.objects.filter(
        cancelado=False,
        data_inicio__gte=hoje,
        data_inicio__lte=hoje + dt.timedelta(days=15),
        termos_autorizacao__isnull=True,
    ).select_related("destino_municipio__estado").order_by("data_inicio")

    grupos = [
        ("Diários de bordo sem KM", prestacoes_sem_km, lambda x: f"Ofício {x}"),
        ("Prestações não iniciadas", list(nao_iniciadas), lambda p: p.servidor.nome),
        ("Ofícios em rascunho", list(rascunhos), lambda o: f"#{o.pk} — {o.assunto or 'sem assunto'}"),
        (
            "Viagens em 15 dias sem termo de autorização",
            list(sem_termo),
            lambda v: f"#{v.pk} {v.destino_display} — {v.periodo_display}",
        ),
    ]

    linhas, total = [], 0
    for titulo, itens, formatar in grupos:
        if not itens:
            continue
        total += len(itens)
        linhas.append(f"{titulo} ({len(itens)}):")
        linhas.extend(f"  • {formatar(item)}" for item in itens[:5])
        if len(itens) > 5:
            linhas.append(f"  … e mais {len(itens) - 5}.")

    if not total:
        return Resultado(titulo="Nenhuma pendência aberta.", dados={"total": 0})
    return Resultado(
        titulo=f"{total} pendência(s):", linhas=linhas, dados={"total": total}
    )


@registrar(
    "preparar_viagem",
    descricao=(
        "Monta uma viagem com roteiro, ofício e termo de autorização em rascunho, "
        "a partir dos dados já confirmados."
    ),
    parametros=(
        Parametro("destino", "inteiro", "Id do município de destino", obrigatorio=True),
        Parametro("origem", "inteiro", "Id do município sede", obrigatorio=True),
        Parametro("data_inicio", "data", "Primeiro dia", obrigatorio=True),
        Parametro("data_fim", "data", "Último dia"),
        Parametro("motivo", "texto", "Motivo da viagem", obrigatorio=True),
        Parametro("servidores", "texto", "Ids dos servidores, separados por vírgula", obrigatorio=True),
        Parametro("motorista", "inteiro", "Id do motorista"),
        Parametro("viatura", "inteiro", "Id da viatura"),
    ),
    mutante=True,
    permissao=pode_preparar_documentos,
)
def preparar_viagem(
    usuario,
    destino,
    origem,
    data_inicio,
    motivo,
    servidores,
    data_fim=None,
    motorista=None,
    viatura=None,
):
    """Cria o conjunto em rascunho — nada é finalizado, nada é numerado.

    O ofício nasce sem número de propósito: a numeração é reserva de recurso
    escasso (``core.numeracao``) e não deve ser gasta por um rascunho que
    talvez seja descartado. Ele recebe número quando a pessoa finalizar pela
    tela, como sempre foi.
    """
    from django.db import transaction

    from cadastros.models import Municipio
    from viagens_cadastros.models import Servidor, Viatura
    from viagens_oficios.models import Oficio
    from viagens_roteiros.models import Roteiro, RoteiroDestino
    from viagens_viagem.models import Viagem
    from viagens_viagem.services import garantir_termo_automatico

    municipio_destino = Municipio.objects.select_related("estado").get(pk=destino)
    municipio_origem = Municipio.objects.select_related("estado").get(pk=origem)
    equipe = list(Servidor.objects.filter(pk__in=[int(s) for s in str(servidores).split(",") if s.strip()]))
    data_fim = data_fim or data_inicio

    with transaction.atomic():
        viagem = Viagem.objects.create(
            titulo=f"{municipio_destino.nome}/{municipio_destino.estado.sigla} — {data_inicio.strftime('%d/%m/%Y')}",
            destino_municipio=municipio_destino,
            destino_estado=municipio_destino.estado,
            data_inicio=data_inicio,
            data_fim=data_fim,
            motivo=motivo,
            status=Viagem.STATUS_EM_PREPARACAO,
        )
        roteiro = Roteiro.objects.create(
            viagem=viagem,
            origem_municipio=municipio_origem,
            quantidade_servidores=max(len(equipe), 1),
        )
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=municipio_destino, ordem=1)

        oficio = Oficio.objects.create(
            viagem=viagem,
            roteiro=roteiro,
            assunto=f"Viagem a {municipio_destino.nome}/{municipio_destino.estado.sigla}",
            motivo=motivo,
            motorista_id=motorista,
            viatura_id=viatura,
        )
        if equipe:
            oficio.servidores.set(equipe)
        garantir_termo_automatico(viagem)

    linhas = [
        f"• Viagem #{viagem.pk} — {viagem.destino_display}, {viagem.periodo_display}",
        f"• Roteiro #{roteiro.pk} — sai de {municipio_origem.nome}/{municipio_origem.estado.sigla}",
        f"• Ofício #{oficio.pk} — {len(equipe)} servidor(es), em rascunho",
        "• Termo de autorização criado em branco",
    ]
    if motorista:
        linhas.append(f"• Motorista: {Servidor.objects.get(pk=motorista).nome}")
    if viatura:
        linhas.append(f"• Viatura: {Viatura.objects.get(pk=viatura).placa}")
    linhas.append("Abra a viagem no sistema para conferir, numerar e gerar os arquivos.")

    return Resultado(
        titulo="Pronto. Criei em rascunho:",
        linhas=linhas,
        dados={"viagem": viagem.pk, "roteiro": roteiro.pk, "oficio": oficio.pk},
    )
