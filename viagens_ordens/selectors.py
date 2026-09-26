"""Consultas de leitura das ordens de serviço, no molde de `viagens_termos/selectors.py`.

Mesmos `prefetch_related` do `ordens_servico/selectors.py` da origem, sem o
recorte por área. Os destinos vêm num `Prefetch` na ordem da OS e com o
estado junto: é o que deixa o presenter usar `ordem.destinos.all()` sem uma
consulta por linha.
"""

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404

from cadastros.models import Municipio

from .abas import anotar_situacao, q_das_abas
from .models import OrdemServico

_DESTINOS_DO_CARTAO = Prefetch("destinos", queryset=Municipio.objects.select_related("estado").order_by("ordemservicodestino__ordem", "ordemservicodestino__pk"))


def base_ordens():
    return anotar_situacao(
        OrdemServico.objects.select_related(
            "viagem",
            "motorista_equipe", "tecnico_equipe", "apoio_montagem", "apoio_escolta",
            "coordenador_cerimonial", "apoio_cerimonial", "apoio_preparacao",
        ).prefetch_related(
            _DESTINOS_DO_CARTAO,
            "servidores__cargo", "servidores__unidade",
            "oficios",
        )
    )


def _filtro_busca(q):
    """Motivo, destino ou servidor; só dígitos casam número, ano ou ofício — o placeholder da origem."""
    q = q.strip()
    filtro = Q(motivo__icontains=q) | Q(destinos__nome__icontains=q) | Q(servidores__nome__icontains=q)
    if q.isdigit():
        filtro |= Q(numero=int(q)) | Q(ano=int(q)) | Q(oficios__numero=int(q))
    elif "/" in q:
        numero, _, ano = q.partition("/")
        if numero.strip().isdigit() and ano.strip().isdigit():
            filtro |= Q(numero=int(numero), ano=int(ano))
    return filtro


def listar_ordens(q="", *, situacoes=None, viagem=None):
    """`viagem` filtra pela FK (o painel da viagem usa); a ordem é a da origem: número maior primeiro."""
    qs = base_ordens()
    if viagem is not None:
        qs = qs.filter(viagem=viagem)
    if q:
        qs = qs.filter(_filtro_busca(q)).distinct()
    filtro = q_das_abas(situacoes)
    if filtro is not None:
        qs = qs.filter(filtro)
    return qs.order_by("-ano", "-numero", "-pk")


def get_ordem_by_id(pk):
    return get_object_or_404(base_ordens(), pk=pk)
