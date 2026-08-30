from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

ITENS_POR_PAGINA = 20


def home(request):
    """Raiz do site: envia para o dashboard (ou login, se não autenticado)."""
    if request.user.is_authenticated:
        return redirect("dashboard:index")
    return redirect("accounts:login")


@login_required
def lista_notificacoes(request):
    """Central de notificações do usuário; abrir marca as exibidas como lidas."""
    queryset = request.user.notificacoes.all()
    pagina = Paginator(queryset, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    # Congela o estado exibido antes de marcar como lidas.
    notificacoes = [
        {"notificacao": item, "nao_lida": not item.lida} for item in pagina
    ]
    request.user.notificacoes.filter(
        pk__in=[item["notificacao"].pk for item in notificacoes], lida=False
    ).update(lida=True)
    return render(
        request,
        "pages/core/notificacoes.html",
        {"pagina": pagina, "notificacoes": notificacoes},
    )
