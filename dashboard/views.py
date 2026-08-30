from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from solicitacoes.models import SolicitacaoEvento, StatusSolicitacao
from solicitacoes.permissions import queryset_visivel


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
        status__in=[
            StatusSolicitacao.ATENDIDA,
            StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
            StatusSolicitacao.NAO_ATENDIDA,
        ],
    ).count()
    deferidas_ano = do_ano.filter(
        status__in=[
            StatusSolicitacao.ATENDIDA,
            StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
        ],
    ).count()
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

    lista = reverse("solicitacoes:lista")
    resumo = [
        {
            "titulo": "Solicitações no mês",
            "valor": no_mes,
            "variacao": (
                f"{abs(diferenca)} em relação ao mês anterior"
                if no_mes_anterior or no_mes
                else "Sem registros"
            ),
            "tendencia": "alta" if diferenca > 0 else "baixa" if diferenca < 0 else "",
            "url": lista,
        },
        {
            "titulo": "Aguardando despacho",
            "valor": aguardando,
            "variacao": "Pendentes de decisão da DG",
            "url": f"{lista}?status={StatusSolicitacao.AGUARDANDO_DESPACHO}",
        },
        {
            "titulo": "Deferidas no ano",
            "valor": deferidas_ano,
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
            "variacao": (
                f"{proximos_unidade_movel} com unidade móvel" if proximos_total else "Nenhum evento agendado"
            ),
            "url": (
                f"{lista}?inicio={hoje:%Y-%m-%d}"
                f"&fim={hoje + timedelta(days=30):%Y-%m-%d}"
            ),
        },
    ]

    ultimas_solicitacoes = visiveis.select_related("municipio", "tipo_evento").order_by(
        "-criado_em"
    )[:5]

    return render(
        request,
        "pages/dashboard/index.html",
        {
            "resumo": resumo,
            "ultimas_solicitacoes": ultimas_solicitacoes,
            "url_lista": lista,
        },
    )
