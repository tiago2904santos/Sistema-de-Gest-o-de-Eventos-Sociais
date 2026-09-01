from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST


def erro_403(request, exception=None):
    """Resposta de acesso negado com orientação e retorno seguro."""
    return render(request, "403.html", status=403)

ITENS_POR_PAGINA = 20


def _metricas_eventos(usuario, hoje):
    from solicitacoes.models import SolicitacaoEvento, StatusSolicitacao
    from solicitacoes.permissions import queryset_visivel

    visiveis = queryset_visivel(usuario, SolicitacaoEvento.objects.all())
    proximos = visiveis.filter(
        data_inicio_evento__gte=hoje,
        data_inicio_evento__lte=hoje + timedelta(days=30),
    ).exclude(
        status__in=[
            StatusSolicitacao.CANCELADA,
            StatusSolicitacao.NAO_ATENDIDA,
        ]
    )
    return [
        {
            "rotulo": "No mês",
            "valor": visiveis.filter(
                data_solicitacao__year=hoje.year, data_solicitacao__month=hoje.month
            ).count(),
        },
        {
            "rotulo": "Aguardando despacho",
            "valor": visiveis.filter(
                status=StatusSolicitacao.AGUARDANDO_DESPACHO
            ).count(),
            "destaque": True,
        },
        {"rotulo": "Eventos em 30 dias", "valor": proximos.count()},
    ]


def _metricas_coffee_break(usuario, hoje):
    from coffee_break import services as coffee_services
    from coffee_break.models import (
        LoteCoffeeBreak,
        SituacaoFinanceira,
        SolicitacaoCoffeeBreak,
    )

    lotes = list(LoteCoffeeBreak.objects.filter(ativo=True).com_consumo())
    restante = sum(lote.restante for lote in lotes)
    em_alerta = len(coffee_services.lotes_em_alerta(lotes))
    pendencias = sum(
        1
        for s in SolicitacaoCoffeeBreak.objects.filter(cancelada=False).only(
            "cancelada",
            "numero_nota_fiscal",
            "protocolo_pagamento",
            "data_atesto_gaf",
            "data_ordem_bancaria",
            "data_envio_empresa",
        )
        if s.situacao_financeira != SituacaoFinanceira.CONCLUIDA
    )
    return [
        {"rotulo": "Saldo dos lotes", "valor": restante},
        {"rotulo": "Pendências financeiras", "valor": pendencias, "destaque": True},
        {"rotulo": "Lotes em alerta", "valor": em_alerta},
    ]


def _metricas_demandas(usuario, hoje):
    from demandas_eventos.models import DemandaEvento, StatusDemanda
    from demandas_eventos.permissions import queryset_visivel

    visiveis = queryset_visivel(usuario, DemandaEvento.objects.all())
    return [
        {
            "rotulo": "Pendentes",
            "valor": visiveis.filter(status=StatusDemanda.PENDENTE).count(),
            "destaque": True,
        },
        {
            "rotulo": "Em andamento",
            "valor": visiveis.filter(
                status__in=[
                    StatusDemanda.EM_ANDAMENTO,
                    StatusDemanda.AGUARDANDO_RETORNO,
                ]
            ).count(),
        },
        {
            "rotulo": "Eventos agendados",
            "valor": visiveis.filter(
                status=StatusDemanda.EVENTO_AGENDADO
            ).count(),
        },
    ]


# Cada módulo do portal sabe calcular os próprios indicadores do hub.
METRICAS_POR_MODULO = {
    "eventos": _metricas_eventos,
    "coffee_break": _metricas_coffee_break,
    "demandas_eventos": _metricas_demandas,
}


def home(request):
    """Raiz do site: portal de módulos (ou login, se não autenticado).

    Camada intermediadora entre o login e os módulos: mostra um panorama do
    que os setores do usuário têm e a entrada de cada módulo. Dentro de um
    módulo, a navegação passa a ser só daquele módulo (navbar contextual).
    """
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    from django.urls import reverse

    from accounts.modulos import modulos_do_portal
    from solicitacoes.permissions import pode_gerenciar_usuarios

    hoje = timezone.localdate()
    cartoes = []
    for modulo in modulos_do_portal(request.user):
        calcular = METRICAS_POR_MODULO.get(modulo["slug"])
        cartoes.append(
            {
                **modulo,
                "url": reverse(modulo["entrada"]),
                "metricas": calcular(request.user, hoje) if calcular else [],
            }
        )

    return render(
        request,
        "pages/core/hub.html",
        {
            "cartoes": cartoes,
            "mostrar_usuarios": pode_gerenciar_usuarios(request.user),
        },
    )


@login_required
def lista_notificacoes(request):
    """Central de notificações: a leitura é explícita (botão ou clique)."""
    todas = request.user.notificacoes.all()
    total = todas.count()
    nao_lidas = todas.filter(lida=False).count()
    filtro = request.GET.get("filtro", "")
    queryset = todas
    if filtro == "nao-lidas":
        queryset = todas.filter(lida=False)
    elif filtro == "lidas":
        queryset = todas.filter(lida=True)
    pagina = Paginator(queryset, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))

    hoje = timezone.localdate()
    ontem = hoje - timedelta(days=1)
    grupos = []
    for item in pagina:
        dia = timezone.localtime(item.criada_em).date()
        if dia == hoje:
            rotulo = "Hoje"
        elif dia == ontem:
            rotulo = "Ontem"
        else:
            rotulo = dia.strftime("%d/%m/%Y")
        if not grupos or grupos[-1]["rotulo"] != rotulo:
            grupos.append({"rotulo": rotulo, "itens": []})
        grupos[-1]["itens"].append(item)

    return render(
        request,
        "pages/core/notificacoes.html",
        {
            "pagina": pagina,
            "grupos": grupos,
            "filtro": filtro,
            "total": total,
            "nao_lidas": nao_lidas,
            "lidas": total - nao_lidas,
        },
    )


@login_required
@require_POST
def marcar_notificacoes_lidas(request):
    request.user.notificacoes.filter(lida=False).update(lida=True)
    return redirect("core:notificacoes")


@login_required
def abrir_notificacao(request, pk):
    """Marca a notificação como lida e segue para o destino dela."""
    notificacao = get_object_or_404(request.user.notificacoes, pk=pk)
    if not notificacao.lida:
        notificacao.lida = True
        notificacao.save(update_fields=["lida"])
    if notificacao.link:
        return redirect(notificacao.link)
    return redirect("core:notificacoes")
