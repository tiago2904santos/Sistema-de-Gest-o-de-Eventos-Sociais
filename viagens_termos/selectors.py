from django.db.models import Q
from django.shortcuts import get_object_or_404

from core.utils.masks import normalize_protocolo
from core.normalizers import normalize_plate

from .abas import anotar_situacao, q_das_abas
from .models import TermoAutorizacao


def base_termos():
    return anotar_situacao(
        TermoAutorizacao.objects.select_related(
            "oficio__roteiro__origem_municipio__estado", "oficio__viatura", "viatura", "destino_cidade__estado", "destino_estado"
        ).prefetch_related(
            "servidores__cargo", "servidores__unidade",
            "oficio__servidores_termo_autorizacao__cargo", "oficio__servidores_termo_autorizacao__unidade",
            "oficio__roteiro__destinos__municipio__estado",
        )
    )


def _filtro_busca(q):
    """Destino, ofício, protocolo, viatura ou servidor — o placeholder da origem."""
    q = q.strip()
    filtro = (
        Q(destino_cidade__nome__icontains=q)
        | Q(destino_estado__sigla__iexact=q)
        | Q(destinos_extras__icontains=q)
        | Q(oficio__roteiro__destinos__municipio__nome__icontains=q)
        | Q(servidores__nome__icontains=q)
        | Q(oficio__servidores_termo_autorizacao__nome__icontains=q)
        | Q(viatura__modelo__icontains=q)
        | Q(oficio__viatura__modelo__icontains=q)
        | Q(oficio__motivo__icontains=q)
    )
    digitos = normalize_protocolo(q)
    if digitos:
        filtro |= Q(oficio__protocolo__icontains=digitos)
    placa = normalize_plate(q)
    if placa:
        filtro |= Q(viatura__placa__icontains=placa) | Q(oficio__viatura__placa__icontains=placa)
    if q.isdigit():
        filtro |= Q(oficio__numero=int(q)) | Q(pk=int(q))
    elif "/" in q:
        numero, _, ano = q.partition("/")
        if numero.strip().isdigit() and ano.strip().isdigit():
            filtro |= Q(oficio__numero=int(numero), oficio__ano=int(ano))
    return filtro


def listar_termos(q="", cancelados=None, *, situacoes=None):
    """`cancelados` é o contrato anterior (True/False); `situacoes` é o da origem."""
    qs = base_termos()
    if cancelados is not None and not situacoes:
        qs = qs.filter(cancelado=bool(cancelados))
    if q:
        qs = qs.filter(_filtro_busca(q)).distinct()
    filtro = q_das_abas(situacoes)
    if filtro is not None:
        qs = qs.filter(filtro)
    return qs.order_by("-criado_em", "-pk")


def get_termo_by_id(pk):
    return get_object_or_404(base_termos(), pk=pk)
