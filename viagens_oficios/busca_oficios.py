"""Busca de ofícios para seletores: até 30 ofícios que casam com o termo.

Era a busca da inclusão rápida de justificativas; hoje quem a usa é o
cadastro de termos (`viagens_termos:api_buscar_oficios`).
"""

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core.utils.masks import format_protocolo
from viagens_cadastros.permissions import acesso_ao_modulo

from .picker import LIMITE_BUSCA, dados_do_option
from .presenters import subtitulo_do_cartao
from .selectors import _filtro_busca, base_oficios


def rotulo_do_oficio(oficio):
    return f"Ofício {oficio.numero_formatado}"


def resumo_para_busca(oficio):
    """O que a busca do seletor enxerga: número, protocolo, viajantes e destinos."""
    partes = [oficio.numero_formatado, format_protocolo(oficio.protocolo), oficio.assunto, oficio.motivo]
    partes += [s.nome for s in oficio.servidores.all()]
    if oficio.roteiro_id:
        partes += [str(d.municipio) for d in oficio.roteiro.destinos.all() if d.municipio_id]
    return {"search_text": " ".join(p for p in partes if p)}


def opcao_do_oficio(oficio):
    dados = dados_do_option(oficio, resumo=resumo_para_busca(oficio), rotulo=rotulo_do_oficio, decorar=True)
    dados["id"] = oficio.pk
    dados["meta"] = " · ".join(p for p in [subtitulo_do_cartao(oficio), dados["meta"]] if p)
    return dados


def oficios_para_escolha():
    return base_oficios().filter(cancelado=False).order_by("-ano", "-numero", "-pk")


@acesso_ao_modulo
@require_GET
def buscar_oficios(request):
    termo = request.GET.get("q", "").strip()
    queryset = oficios_para_escolha()
    if termo:
        queryset = queryset.filter(_filtro_busca(termo)).distinct()
    resultados = [opcao_do_oficio(o) for o in queryset[:LIMITE_BUSCA]]
    return JsonResponse({"results": resultados, "limite": LIMITE_BUSCA, "truncado": queryset.count() > LIMITE_BUSCA})
