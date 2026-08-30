from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
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

    # Deferidas em andamento contam como decisão favorável da DG.
    finalizadas_ano = visiveis.filter(
        data_solicitacao__year=hoje.year,
        status__in=[
            StatusSolicitacao.ATENDIDA,
            StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
            StatusSolicitacao.NAO_ATENDIDA,
        ],
    ).count()
    atendidas_ano = visiveis.filter(
        data_solicitacao__year=hoje.year,
        status__in=[
            StatusSolicitacao.ATENDIDA,
            StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
        ],
    ).count()
    percentual = round(atendidas_ano * 100 / finalizadas_ano) if finalizadas_ano else 0

    proximos = visiveis.filter(
        data_inicio_evento__gte=hoje,
        data_inicio_evento__lte=hoje + timedelta(days=30),
    ).exclude(
        status__in=[StatusSolicitacao.CANCELADA, StatusSolicitacao.NAO_ATENDIDA]
    )
    proximos_total = proximos.count()
    proximos_unidade_movel = proximos.filter(unidade_movel=True).count()

    resumo = [
        {
            "titulo": "Solicitações no mês",
            "valor": no_mes,
            "variacao": (
                f"{diferenca:+d} em relação ao mês anterior" if no_mes_anterior or no_mes else "Sem registros"
            ),
        },
        {
            "titulo": "Aguardando despacho",
            "valor": aguardando,
            "variacao": "Pendentes de decisão da DG",
        },
        {
            "titulo": "Atendidas no ano",
            "valor": atendidas_ano,
            "variacao": (
                f"{percentual}% das finalizadas" if finalizadas_ano else "Nenhuma finalizada ainda"
            ),
        },
        {
            "titulo": "Eventos nos próximos 30 dias",
            "valor": proximos_total,
            "variacao": (
                f"{proximos_unidade_movel} com unidade móvel" if proximos_total else "Nenhum evento agendado"
            ),
        },
    ]

    ultimas_solicitacoes = visiveis.select_related("municipio", "tipo_evento").order_by(
        "-criado_em"
    )[:5]

    return render(
        request,
        "pages/dashboard/index.html",
        {"resumo": resumo, "ultimas_solicitacoes": ultimas_solicitacoes},
    )
