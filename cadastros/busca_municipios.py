"""Busca de municípios conforme a pessoa digita (m075).

Os seletores de município embutiam a base inteira (5.570 nomes do IBGE) em
cada campo da página; no modo remoto do `components/select.html` eles trazem
só o que está escolhido e pedem o resto aqui. A comparação ignora acento e
caixa, como o filtro do próprio seletor: "sao" acha "São Paulo".
"""

import unicodedata

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Municipio

LIMITE = 20


def _normalizar(texto):
    sem_acento = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).casefold().strip()


def opcao_de_municipio(municipio):
    """O formato de opção do `components/select.html`, com o estado para a cascata."""
    return {"valor": str(municipio.pk), "rotulo": municipio.nome, "estado": str(municipio.estado_id)}


def opcoes_dos_municipios(ids):
    """Opções só dos municípios já escolhidos — o ponto de partida do modo remoto."""
    chaves = {int(i) for i in (str(v).strip() for v in ids if v not in (None, "")) if i.isdigit()}
    if not chaves:
        return []
    return [opcao_de_municipio(m) for m in Municipio.objects.filter(pk__in=chaves).order_by("nome")]


def buscar(termo="", estado_id=None, limite=LIMITE):
    """Municípios ativos cujo nome contém o termo; os que começam com ele primeiro."""
    base = Municipio.objects.filter(ativo=True)
    if estado_id:
        base = base.filter(estado_id=estado_id)
    alvo = _normalizar(termo)
    comeca, contem = [], []
    for pk, nome, estado in base.order_by("nome").values_list("pk", "nome", "estado_id"):
        chave = _normalizar(nome)
        if not alvo or chave.startswith(alvo):
            comeca.append((pk, nome, estado))
            if len(comeca) >= limite:
                break
        elif alvo in chave:
            contem.append((pk, nome, estado))
    return [
        {"valor": str(pk), "rotulo": nome, "estado": str(estado)}
        for pk, nome, estado in (comeca + contem)[:limite]
    ]


@login_required
@require_GET
def buscar_municipios(request):
    estado = request.GET.get("uf", "").strip()
    estado_id = int(estado) if estado.isdigit() else None
    return JsonResponse({"resultados": buscar(request.GET.get("q", ""), estado_id)})
