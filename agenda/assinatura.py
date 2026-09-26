"""Assinar a Agenda: o link pessoal do feed iCalendar e o feed em si.

Duas rotas. `feed_ics` é pública — o Outlook e o Google Agenda buscam o
arquivo sem sessão — e o token é a única credencial: um token desconhecido
é 404 seco, sem dizer se existe usuário. `assinatura` (POST, com login)
gera, troca ou revoga o link da própria pessoa; a tela é o modal "Assinar"
do painel da agenda.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import AssinaturaAgenda

from . import ics
from .fontes import fontes_de


def _slugs(valor: str | None) -> list[str]:
    return [s.strip() for s in (valor or "").split(",") if s.strip()]


def feed_ics(request, token):
    assinatura = (
        AssinaturaAgenda.objects.select_related("usuario")
        .filter(token=token, usuario__is_active=True)
        .first()
    )
    if assinatura is None:
        raise Http404
    texto = ics.feed(
        assinatura.usuario,
        slugs=_slugs(request.GET.get("fontes")),
        so_meus=request.GET.get("meus") in ("1", "true", "sim"),
        dominio=request.get_host().split(":")[0] or "agenda",
        base_url=request.build_absolute_uri("/").rstrip("/"),
    )
    resposta = HttpResponse(texto, content_type="text/calendar; charset=utf-8")
    resposta["Content-Disposition"] = 'inline; filename="agenda.ics"'
    resposta["Cache-Control"] = "private, max-age=300"
    return resposta


def contexto_assinatura(request) -> dict:
    """O que o modal "Assinar" precisa: o link atual (se houver) e as fontes."""
    assinatura = AssinaturaAgenda.objects.filter(usuario=request.user).first()
    url = ""
    if assinatura is not None:
        url = request.build_absolute_uri(reverse("agenda:ics", args=[assinatura.token]))
    return {
        "assinatura_url": url,
        "assinatura_gerada_em": assinatura.gerado_em if assinatura else None,
        "url_assinatura": reverse("agenda:assinatura"),
        "fontes_assinatura": fontes_de(request.user),
    }


@login_required
@require_POST
def assinatura(request):
    acao = request.POST.get("acao", "gerar")
    if acao == "revogar":
        apagados, _ = AssinaturaAgenda.objects.filter(usuario=request.user).delete()
        messages.success(request, "Link de assinatura revogado." if apagados else "Não havia link para revogar.")
    else:
        existia = AssinaturaAgenda.objects.filter(usuario=request.user).exists()
        AssinaturaAgenda.gerar(request.user)
        messages.success(
            request,
            "Novo link gerado; o anterior deixou de valer." if existia else "Link de assinatura gerado.",
        )
    return redirect(reverse("agenda:painel") + "#assinar")
