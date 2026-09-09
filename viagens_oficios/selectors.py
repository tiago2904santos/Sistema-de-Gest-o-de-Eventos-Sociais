from django.db.models import Q
from django.shortcuts import get_object_or_404
from .models import Oficio, ModeloMotivoOficio


def listar_oficios(q='', status='', ano='', fila=''):
    qs = Oficio.objects.select_related('roteiro', 'solicitante', 'viatura').prefetch_related('servidores', 'roteiro__destinos__municipio')
    if q:
        filtro = Q(protocolo__icontains=q) | Q(motivo__icontains=q) | Q(servidores__nome__icontains=q)
        if q.isdigit():
            filtro |= Q(numero=int(q))
        qs = qs.filter(filtro).distinct()
    if status in dict(Oficio.STATUS_CHOICES):
        qs = qs.filter(status=status)
    if str(ano).isdigit():
        qs = qs.filter(ano=int(ano))
    if fila == 'cancelados':
        qs = qs.filter(cancelado=True)
    elif fila != 'todos':
        qs = qs.filter(cancelado=False)
    return qs


def get_oficio_by_id(pk):
    return get_object_or_404(listar_oficios(fila='todos'), pk=pk)


def listar_modelos_motivo_ativos():
    return ModeloMotivoOficio.objects.filter(ativo=True)
