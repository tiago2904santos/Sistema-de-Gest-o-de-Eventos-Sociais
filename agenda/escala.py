"""A escala: uma linha por pessoa, uma coluna por dia (m134).

Responde "quem está fora na quinta?" sem abrir ofício por ofício. É uma
tabela HTML própria, montada dos mesmos compromissos do calendário
(`eventos_de`, com ``extendedProps.pessoas``), e por isso com as mesmas
permissões: quem não vê Viagens não vê a escala das viagens. Sem plugin
de linha do tempo — a tabela resolve e imprime.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from .fontes import FONTES, eventos_de, fontes_de

#: Quantos dias cabem numa escala: uma semana por padrão, dois meses no máximo.
DIAS_PADRAO = 7
DIAS_MAXIMO = 62
OPCOES_DIAS = (7, 14, 31)

_ROTULOS = {f.slug: f.rotulo for f in FONTES}
_DIAS_SEMANA = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def _data(valor, padrao: dt.date) -> dt.date:
    try:
        return dt.date.fromisoformat((valor or "")[:10])
    except ValueError:
        return padrao


def _dias(valor) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return DIAS_PADRAO
    return max(1, min(n, DIAS_MAXIMO))


def montar(usuario, inicio: dt.date, dias: int, *, slugs=None, pessoa: str = "", hoje: dt.date | None = None) -> dict:
    """As linhas da escala no período [inicio, inicio + dias)."""
    hoje = hoje or timezone.localdate()
    fim = inicio + dt.timedelta(days=dias)
    colunas = []
    for i in range(dias):
        d = inicio + dt.timedelta(days=i)
        colunas.append({"data": d, "semana": _DIAS_SEMANA[d.weekday()], "fim_de_semana": d.weekday() >= 5, "hoje": d == hoje})

    filtro = (pessoa or "").strip().casefold()
    linhas: dict[str, dict] = {}
    for ev in eventos_de(usuario, inicio, fim, slugs):
        props = ev["extendedProps"]
        nomes = props.get("pessoas") or []
        if not nomes:
            continue
        ev_inicio = max(dt.date.fromisoformat(ev["start"]), inicio)
        ev_fim = min(dt.date.fromisoformat(ev["end"]), fim)  # exclusivo
        if ev_fim <= ev_inicio:
            continue
        item = {
            "fonte": props["fonte"],
            "rotulo": _ROTULOS.get(props["fonte"], props["fonte"]),
            "titulo": ev["title"],
            "situacao": props.get("situacao", ""),
            "encerrado": bool(props.get("encerrado")),
            "url": props.get("url", ""),
            "numero": props.get("numero"),
        }
        for nome in nomes:
            if filtro and filtro not in nome.casefold():
                continue
            linha = linhas.setdefault(nome, {"nome": nome, "celulas": [[] for _ in range(dias)], "total": 0})
            linha["total"] += 1
            d = ev_inicio
            while d < ev_fim:
                linha["celulas"][(d - inicio).days].append(item)
                d += dt.timedelta(days=1)
    ordenadas = sorted(linhas.values(), key=lambda l: l["nome"].casefold())
    for linha in ordenadas:
        linha["dias_fora"] = sum(1 for c in linha["celulas"] if any(not i["encerrado"] for i in c))
    return {"colunas": colunas, "linhas": ordenadas, "inicio": inicio, "fim": fim - dt.timedelta(days=1), "dias": dias}


def _url(inicio: dt.date, dias: int, pessoa: str, fontes: str) -> str:
    params = {"inicio": inicio.isoformat(), "dias": str(dias)}
    if pessoa:
        params["pessoa"] = pessoa
    if fontes:
        params["fontes"] = fontes
    return reverse("agenda:escala") + "?" + urlencode(params)


@login_required
def escala(request):
    hoje = timezone.localdate()
    segunda = hoje - dt.timedelta(days=hoje.weekday())
    inicio = _data(request.GET.get("inicio"), segunda)
    dias = _dias(request.GET.get("dias"))
    pessoa = (request.GET.get("pessoa") or "").strip()[:120]
    fontes = (request.GET.get("fontes") or "").strip()
    slugs = [s for s in fontes.split(",") if s.strip()]
    quadro = montar(request.user, inicio, dias, slugs=slugs, pessoa=pessoa, hoje=hoje)
    quadro.update({
        "pessoa": pessoa,
        "fontes_texto": fontes,
        "fontes": [{"slug": f.slug, "rotulo": f.rotulo, "ligada": not slugs or f.slug in slugs} for f in fontes_de(request.user)],
        "opcoes_dias": [{"n": n, "ativo": n == dias, "url": _url(inicio, n, pessoa, fontes)} for n in OPCOES_DIAS],
        "url_anterior": _url(inicio - dt.timedelta(days=dias), dias, pessoa, fontes),
        "url_proximo": _url(inicio + dt.timedelta(days=dias), dias, pessoa, fontes),
        "url_hoje": _url(segunda, dias, pessoa, fontes),
        "url_agenda": reverse("agenda:painel"),
        "hoje": hoje,
    })
    return render(request, "pages/agenda/escala.html", quadro)
