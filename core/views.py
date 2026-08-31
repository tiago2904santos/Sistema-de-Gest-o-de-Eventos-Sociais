from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

ITENS_POR_PAGINA = 20


def home(request):
    """Raiz do site: envia para o dashboard (ou login, se não autenticado)."""
    if request.user.is_authenticated:
        return redirect("dashboard:index")
    return redirect("accounts:login")


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
