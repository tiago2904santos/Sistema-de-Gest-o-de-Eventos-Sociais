from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Min, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from solicitacoes.models import (
    AcaoHistorico,
    DecisaoDG,
    HistoricoSolicitacao,
    SolicitacaoEvento,
    StatusSolicitacao,
)
from solicitacoes.permissions import queryset_visivel

MESES_ABREVIADOS = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]

PERIODOS_GRAFICO = [
    {"valor": 6, "rotulo": "Últimos 6 meses"},
    {"valor": 12, "rotulo": "Últimos 12 meses"},
    {"valor": 24, "rotulo": "Últimos 24 meses"},
]

STATUS_DEFERIDOS = [
    StatusSolicitacao.ATENDIDA,
    StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
]


def _meses_recentes(hoje, quantidade):
    """Primeiro dia de cada um dos últimos `quantidade` meses, do mais antigo."""
    ancora = hoje.replace(day=1)
    meses = []
    for recuo in range(quantidade - 1, -1, -1):
        ano = ancora.year + (ancora.month - 1 - recuo) // 12
        mes = (ancora.month - 1 - recuo) % 12 + 1
        meses.append(ancora.replace(year=ano, month=mes))
    return meses


def _serie_mensal(queryset, campo, meses):
    """Contagem por mês de `campo` alinhada à lista `meses` (zeros incluídos)."""
    contagens = dict(
        queryset.filter(
            **{f"{campo}__gte": meses[0], f"{campo}__isnull": False}
        )
        .annotate(mes=TruncMonth(campo))
        .values("mes")
        .annotate(total=Count("pk"))
        .values_list("mes", "total")
    )
    return [contagens.get(mes, 0) for mes in meses]


def _sparkline(valores):
    """Alturas percentuais das barras; zero fica visível como toco mínimo."""
    maior = max(valores) if any(valores) else 1
    return [
        {"altura": max(round(valor * 100 / maior), 6) if valor else 6, "valor": valor}
        for valor in valores
    ]


@login_required
def index(request):
    """Dashboard com indicadores calculados do banco."""
    hoje = timezone.localdate()
    visiveis = queryset_visivel(request.user, SolicitacaoEvento.objects.all())

    inicio_mes = hoje.replace(day=1)
    mes_anterior_fim = inicio_mes - timedelta(days=1)

    no_mes = visiveis.filter(
        data_solicitacao__year=hoje.year, data_solicitacao__month=hoje.month
    ).count()
    no_mes_anterior = visiveis.filter(
        data_solicitacao__year=mes_anterior_fim.year,
        data_solicitacao__month=mes_anterior_fim.month,
    ).count()
    diferenca = no_mes - no_mes_anterior

    aguardando = visiveis.filter(
        status=StatusSolicitacao.AGUARDANDO_DESPACHO
    ).count()

    # "Deferida em andamento" é decisão favorável com evento ainda por vir;
    # "Atendida" é evento realizado e confirmado. Os dois números aparecem
    # separados para o cartão não prometer atendimento que ainda não houve.
    do_ano = visiveis.filter(data_solicitacao__year=hoje.year)
    decididas_ano = do_ano.filter(
        status__in=STATUS_DEFERIDOS + [StatusSolicitacao.NAO_ATENDIDA],
    ).count()
    deferidas_ano = do_ano.filter(status__in=STATUS_DEFERIDOS).count()
    atendidas_ano = do_ano.filter(status=StatusSolicitacao.ATENDIDA).count()
    percentual = round(deferidas_ano * 100 / decididas_ano) if decididas_ano else 0

    proximos = visiveis.filter(
        data_inicio_evento__gte=hoje,
        data_inicio_evento__lte=hoje + timedelta(days=30),
    ).exclude(
        status__in=[StatusSolicitacao.CANCELADA, StatusSolicitacao.NAO_ATENDIDA]
    )
    proximos_total = proximos.count()
    proximos_unidade_movel = proximos.filter(unidade_movel=True).count()

    # Séries mensais do último ano: sustentam as sparklines dos cartões.
    meses_spark = _meses_recentes(hoje, 12)
    serie_todas = _serie_mensal(visiveis, "data_solicitacao", meses_spark)
    serie_aguardando = _serie_mensal(
        visiveis.filter(status=StatusSolicitacao.AGUARDANDO_DESPACHO),
        "data_solicitacao",
        meses_spark,
    )
    serie_deferidas = _serie_mensal(
        visiveis.filter(status__in=STATUS_DEFERIDOS), "data_solicitacao", meses_spark
    )
    serie_eventos = _serie_mensal(
        visiveis.exclude(
            status__in=[StatusSolicitacao.CANCELADA, StatusSolicitacao.NAO_ATENDIDA]
        ),
        "data_inicio_evento",
        meses_spark,
    )

    lista = reverse("solicitacoes:lista")
    resumo = [
        {
            "titulo": "Solicitações no mês",
            "valor": no_mes,
            "icone": "document",
            "cor": "neutra",
            "sparkline": _sparkline(serie_todas),
            "variacao": (
                f"{abs(diferenca)} vs. mês anterior"
                if no_mes_anterior or no_mes
                else "Sem registros"
            ),
            "tendencia": "alta" if diferenca > 0 else "baixa" if diferenca < 0 else "",
            # Menos solicitações não é má notícia por si — a seta informa,
            # sem pintar de vermelho.
            "tendencia_neutra": True,
            "url": lista,
        },
        {
            "titulo": "Aguardando despacho",
            "valor": aguardando,
            "icone": "hourglass",
            "cor": "dourada",
            # O único cartão que pede ação da DG hoje — por isso o destaque.
            "destaque": True,
            "sparkline": _sparkline(serie_aguardando),
            "variacao": "Pendentes de decisão da DG",
            "url": f"{lista}?status={StatusSolicitacao.AGUARDANDO_DESPACHO}",
        },
        {
            "titulo": "Deferidas no ano",
            "valor": deferidas_ano,
            "icone": "check-circle",
            "cor": "sucesso",
            "sparkline": _sparkline(serie_deferidas),
            "variacao": (
                f"{atendidas_ano} já atendidas · {percentual}% das decididas"
                if decididas_ano
                else "Nenhuma decisão registrada ainda"
            ),
            "url": f"{lista}?status={StatusSolicitacao.DEFERIDA_EM_ANDAMENTO}",
        },
        {
            "titulo": "Eventos nos próximos 30 dias",
            "valor": proximos_total,
            "icone": "calendar",
            "cor": "info",
            "sparkline": _sparkline(serie_eventos),
            "variacao": (
                f"{proximos_unidade_movel} com unidade móvel" if proximos_total else "Nenhum evento agendado"
            ),
            "url": (
                f"{lista}?inicio={hoje:%Y-%m-%d}"
                f"&fim={hoje + timedelta(days=30):%Y-%m-%d}"
            ),
        },
    ]

    # Gráfico de solicitações por mês, com o período escolhido pelo usuário.
    try:
        meses_grafico = int(request.GET.get("meses", 12))
    except (TypeError, ValueError):
        meses_grafico = 12
    if meses_grafico not in {periodo["valor"] for periodo in PERIODOS_GRAFICO}:
        meses_grafico = 12

    meses = _meses_recentes(hoje, meses_grafico)
    serie_grafico = _serie_mensal(visiveis, "data_solicitacao", meses)
    teto = max(serie_grafico + [1])
    teto = ((teto + 9) // 10) * 10 if teto > 5 else 5
    grafico = {
        "barras": [
            {
                "rotulo": MESES_ABREVIADOS[mes.month - 1],
                "valor": valor,
                # Inteiro de propósito: float renderiza "66,7" em pt-BR e o
                # CSS descarta a altura.
                "altura": round(valor * 100 / teto),
                "titulo": f"{MESES_ABREVIADOS[mes.month - 1]}/{mes.year}: {valor}",
            }
            for mes, valor in zip(meses, serie_grafico)
        ],
        "eixo": [teto, teto * 2 // 3, teto // 3, 0],
        "meses": meses_grafico,
        "atualizado_em": timezone.localtime(),
    }

    ultimas_solicitacoes = visiveis.select_related("municipio", "tipo_evento").order_by(
        "-criado_em"
    )[:6]

    # Próximos eventos: os mesmos 30 dias do cartão, em ordem de data.
    proximos_eventos = proximos.select_related("municipio", "tipo_evento").order_by(
        "data_inicio_evento", "pk"
    )[:7]

    # Despacho da DG: tempo médio entre envio e decisão, com a mesma regra da
    # vw_tempos_workflow (primeiro ENVIO e primeira DECISAO do histórico).
    marcos = (
        HistoricoSolicitacao.objects.filter(solicitacao__in=visiveis)
        .values("solicitacao_id")
        .annotate(
            enviado_em=Min("criado_em", filter=Q(acao=AcaoHistorico.ENVIO)),
            decidido_em=Min("criado_em", filter=Q(acao=AcaoHistorico.DECISAO)),
        )
        .filter(enviado_em__isnull=False, decidido_em__isnull=False)
    )
    dias = [
        (marco["decidido_em"] - marco["enviado_em"]).total_seconds() / 86400
        for marco in marcos
        if marco["decidido_em"] >= marco["enviado_em"]
    ]
    por_decisao = dict(
        do_ano.values_list("decisao_dg").annotate(total=Count("pk")).values_list(
            "decisao_dg", "total"
        )
    )
    despacho = {
        "media_dias": round(sum(dias) / len(dias), 1) if dias else None,
        "decididas": len(dias),
        "pendentes": aguardando,
        "atender": por_decisao.get(DecisaoDG.ATENDER, 0),
        "nao_atender": por_decisao.get(DecisaoDG.NAO_ATENDER, 0),
        "cancelados": por_decisao.get(DecisaoDG.CANCELADO, 0),
        "ano": hoje.year,
    }

    return render(
        request,
        "pages/dashboard/index.html",
        {
            "resumo": resumo,
            "grafico": grafico,
            "periodos_grafico": PERIODOS_GRAFICO,
            "ultimas_solicitacoes": ultimas_solicitacoes,
            "proximos_eventos": proximos_eventos,
            "despacho": despacho,
            "url_lista": lista,
            "url_despacho": f"{lista}?status={StatusSolicitacao.AGUARDANDO_DESPACHO}",
        },
    )
