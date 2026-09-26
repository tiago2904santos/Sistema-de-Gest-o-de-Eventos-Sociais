"""Views públicas (sem login) do pedido de palestra — ver pedido_publico.py."""

from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from core.limite import cabecalhos_de_pagina_com_token

from . import pedido_publico
from .pedido_publico import AVISO_LGPD, PedidoPublicoForm

CHAVE_SESSAO = "pedido_publico_recebido"


def _tela(request, form, erro="", status=200):
    return render(
        request,
        "pages/publico/pedido_form.html",
        {"form": form, "erro": erro, "aviso_lgpd": AVISO_LGPD, "carimbo": pedido_publico.novo_carimbo()},
        status=status,
    )


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def pedido(request):
    if request.method != "POST":
        return _tela(request, PedidoPublicoForm())
    ip = pedido_publico.ip_do_cliente(request)
    if pedido_publico.bloqueado(ip):
        return _tela(
            request, PedidoPublicoForm(),
            "Recebemos muitos envios deste endereço em pouco tempo. Tente de novo mais tarde.",
            status=429,
        )
    pedido_publico.registrar_tentativa(ip)
    form = PedidoPublicoForm(request.POST, request.FILES)
    # Robô que preencheu a isca: parece que deu certo, mas nada é gravado.
    if form.isca_preenchida:
        request.session[CHAVE_SESSAO] = {}
        return redirect("pedido_publico:recebido")
    motivo = pedido_publico.conferir_carimbo(request.POST.get("carimbo"))
    if motivo:
        erro = (
            "O formulário ficou aberto por muito tempo. Confira os dados e envie de novo."
            if motivo == "expirado"
            else "Confira os dados e envie de novo."
        )
        return _tela(request, form, erro)
    if not form.is_valid():
        return _tela(request, form, "Corrija os campos destacados para enviar.")
    demanda, token = pedido_publico.criar_pedido(form.cleaned_data)
    pedido_publico.registrar_pedido_aceito(ip)
    request.session[CHAVE_SESSAO] = {
        "numero": demanda.pk,
        "link": request.build_absolute_uri(reverse("pedido_publico:acompanhar", args=[token])),
    }
    return redirect("pedido_publico:recebido")


@never_cache
def recebido(request):
    """A confirmação: só o número do pedido e o link de acompanhamento, uma vez."""
    dados = request.session.pop(CHAVE_SESSAO, None)
    if dados is None:
        return redirect("pedido_publico:pedido")
    return cabecalhos_de_pagina_com_token(
        render(request, "pages/publico/pedido_recebido.html", {"recebido": dados})
    )


@never_cache
def acompanhar(request, token):
    demanda = pedido_publico.demanda_do_token(token)
    if demanda is None:
        raise Http404
    return cabecalhos_de_pagina_com_token(render(
        request,
        "pages/publico/pedido_acompanhar.html",
        {
            "numero": demanda.pk,
            "tipo": demanda.get_evento_display(),
            "data_pedido": demanda.data_solicitacao,
            "situacao": pedido_publico.SITUACAO_PUBLICA.get(demanda.status, "Em análise"),
            "agendado": demanda.status == "EVENTO_AGENDADO",
            "data_evento": demanda.data_inicio_evento,
            "hora_evento": demanda.hora_inicio,
        },
    ))
