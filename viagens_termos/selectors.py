from django.db.models import Q
from django.shortcuts import get_object_or_404
from .models import TermoAutorizacao


def listar_termos(q='', cancelados=False):
    qs = TermoAutorizacao.objects.select_related('oficio__roteiro', 'viatura', 'destino_cidade__estado', 'destino_estado').prefetch_related('servidores__cargo', 'servidores__unidade', 'oficio__servidores_termo_autorizacao', 'oficio__roteiro__destinos__municipio__estado')
    qs = qs.filter(cancelado=cancelados)
    if q:
        qs = qs.filter(Q(servidores__nome__icontains=q) | Q(destino_cidade__nome__icontains=q) | Q(oficio__protocolo__icontains=q)).distinct()
    return qs


def get_termo_by_id(pk):
    return get_object_or_404(TermoAutorizacao, pk=pk)
