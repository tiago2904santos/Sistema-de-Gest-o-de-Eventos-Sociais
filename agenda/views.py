"""A agenda: uma tela e um endpoint.

A tela só monta o esqueleto — filtros e o lugar do calendário. Quem preenche
é o endpoint ``eventos``, chamado pelo calendário a cada mudança de mês ou de
visão, com o período visível. Separar assim é o que deixa a navegação
instantânea: trocar de mês não recarrega a página, e o servidor só monta os
compromissos daquele intervalo.

O período tem teto. Uma visão de ano pede doze meses de uma vez; acima disso
é alguém pedindo o banco inteiro por engano ou de propósito — e as duas
coisas merecem a mesma resposta.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from . import detalhes
from .fontes import eventos_de, fontes_de

# Um ano e pouco: cobre a visão anual com folga e nada além.
MAX_DIAS = 400


def _data(valor: str | None) -> dt.date | None:
    """O calendário manda ISO com fuso ("2026-09-01T00:00:00-03:00"); só a data importa."""
    if not valor:
        return None
    try:
        return dt.date.fromisoformat(valor[:10])
    except ValueError:
        return None


@login_required
def painel(request):
    fontes = fontes_de(request.user)
    return render(
        request,
        "pages/agenda/painel.html",
        {
            "fontes": fontes,
            "url_eventos": reverse("agenda:eventos"),
            # Com marcadores: o JS troca "/f/0/" pela fonte e pelo número.
            "url_detalhe": reverse("agenda:detalhe", args=["f", 0]),
            "hoje": timezone.localdate().isoformat(),
        },
    )


@login_required
def eventos(request):
    inicio = _data(request.GET.get("start"))
    fim = _data(request.GET.get("end"))
    if inicio is None or fim is None or fim <= inicio:
        return JsonResponse({"erro": "Informe start e end como datas ISO, com end depois de start."}, status=400)
    if (fim - inicio).days > MAX_DIAS:
        return JsonResponse({"erro": f"Período grande demais: o máximo é {MAX_DIAS} dias."}, status=400)

    pedidas = [s for s in (request.GET.get("fontes") or "").split(",") if s.strip()]
    return JsonResponse(eventos_de(request.user, inicio, fim, pedidas), safe=False)


@login_required
def detalhe(request, fonte, pk):
    """O dossiê de um compromisso, já desenhado, para o modal da agenda.

    Devolve só o miolo (sem o shell): quem pede é o JS, por fetch. A permissão
    é conferida por ``detalhes.montar`` com a regra do módulo de origem; fora
    do acesso vira 403 com um texto curto, que o modal mostra como está.
    """
    try:
        contexto = detalhes.montar(request.user, fonte, pk)
    except PermissionDenied:
        return HttpResponseForbidden("Este compromisso está fora do seu acesso.")
    contexto["total_documentos"] = sum(len(g["itens"]) for g in contexto["documentos"])
    return render(request, "pages/agenda/_detalhe.html", contexto)
