"""Consultas de leitura dos planos de trabalho, no molde dos termos."""

from django.db.models import Max, Min, Q
from django.shortcuts import get_object_or_404

from .abas import anotar_situacao, q_das_abas
from .models import EventoPlano, PlanoTrabalho


def base_planos():
    return anotar_situacao(
        PlanoTrabalho.objects.select_related(
            "programa", "destino_cidade__estado", "destino_estado", "viagem",
            "coordenador_adm__cargo", "coordenador_op__cargo",
        ).prefetch_related("destinos__cidade__estado", "efetivos", "eventos__programa", "eventos__efetivos")
    )


def _filtro_busca(q):
    """Destino, programa ou contextualização — e número/ano quando se digita um número."""
    q = q.strip()
    filtro = (
        Q(destino_cidade__nome__icontains=q)
        | Q(destinos__cidade__nome__icontains=q)
        | Q(programa__nome__icontains=q)
        | Q(programa_outros__icontains=q)
        | Q(eventos__programa__nome__icontains=q)
        | Q(eventos__programa_outros__icontains=q)
        | Q(contextualizacao__icontains=q)
    )
    if q.isdigit():
        filtro |= Q(numero=int(q)) | Q(ano=int(q))
    elif "/" in q:
        numero, _, ano = q.partition("/")
        if numero.strip().isdigit() and ano.strip().isdigit():
            filtro |= Q(numero=int(numero), ano=int(ano))
    return filtro


def listar_planos(q="", *, situacoes=None, viagem=None):
    qs = base_planos()
    if viagem is not None:
        qs = qs.filter(viagem=viagem)
    if q:
        qs = qs.filter(_filtro_busca(q)).distinct()
    filtro = q_das_abas(situacoes)
    if filtro is not None:
        qs = qs.filter(filtro)
    return qs.order_by("-ano", "-numero", "-criado_em")


def get_plano_by_id(pk):
    return get_object_or_404(
        PlanoTrabalho.objects.select_related(
            "programa", "destino_estado", "destino_cidade__estado", "viagem",
            "coordenador_adm__cargo", "coordenador_op__cargo", "evento_em_edicao",
        ),
        pk=pk,
    )


def get_evento_do_plano_by_id(plano, pk):
    return get_object_or_404(EventoPlano, pk=pk, plano=plano)


def obter_intervalo_dos_oficios_da_viagem(plano):
    """O deslocamento coberto pelos ofícios ativos da viagem: primeira saída e última chegada.

    Serve de sugestão para a saída e a chegada na sede, só nas lacunas.
    """
    if not plano.viagem_id:
        return None
    from viagens_oficios.models import Oficio

    intervalo = Oficio.objects.filter(
        viagem_id=plano.viagem_id, cancelado=False, roteiro__isnull=False, roteiro__cancelado=False,
    ).aggregate(saida=Min("roteiro__saida_dt"), chegada=Max("roteiro__retorno_chegada_dt"))
    if not intervalo["saida"] or not intervalo["chegada"] or intervalo["chegada"] <= intervalo["saida"]:
        return None
    return intervalo
