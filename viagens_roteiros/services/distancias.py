"""Distâncias entre municípios guardadas de forma permanente (m078).

Uma fonte só para roteiro e diário de bordo: a tabela ``DistanciaMunicipios``,
alimentada pelo serviço de rotas (cada estimativa nova) e pelos trechos já
gravados nos roteiros. Nada aqui chama serviço externo — quem chama é
``rota.estimar_trecho``, que antes consulta esta tabela.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db.models import Q

from ..models import DistanciaMunicipios


def _decimal(valor):
    if valor in ("", None):
        return None
    try:
        numero = Decimal(str(valor).replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero >= 0 else None


def buscar(origem_id, destino_id):
    """A distância gravada para o par, em qualquer sentido; o sentido exato vence."""
    if not origem_id or not destino_id:
        return None
    candidatos = list(
        DistanciaMunicipios.objects.filter(
            Q(origem_id=origem_id, destino_id=destino_id)
            | Q(origem_id=destino_id, destino_id=origem_id)
        )
    )
    candidatos.sort(key=lambda d: 0 if d.origem_id == origem_id else 1)
    return candidatos[0] if candidatos else None


def registrar(origem_id, destino_id, distancia_km, *, fonte, duracao_min=None, tempo_viagem_min=None):
    """Grava (ou atualiza) a distância do par. Uma correção manual não é sobrescrita.

    Devolve o registro (ou ``None`` quando não há o que gravar).
    """
    distancia = _decimal(distancia_km)
    if not origem_id or not destino_id or origem_id == destino_id or distancia is None:
        return None
    existente = DistanciaMunicipios.objects.filter(origem_id=origem_id, destino_id=destino_id).first()
    if existente is None:
        return DistanciaMunicipios.objects.create(
            origem_id=origem_id,
            destino_id=destino_id,
            distancia_km=distancia,
            duracao_min=duracao_min,
            tempo_viagem_min=tempo_viagem_min,
            fonte=fonte,
        )
    manual = DistanciaMunicipios.Fonte.MANUAL
    if existente.fonte == manual and fonte != manual:
        return existente
    existente.distancia_km = distancia
    existente.fonte = fonte
    if duracao_min is not None:
        existente.duracao_min = duracao_min
    if tempo_viagem_min is not None:
        existente.tempo_viagem_min = tempo_viagem_min
    existente.save()
    return existente


def corrigir(origem_id, destino_id, distancia_km):
    """Correção manual feita pelo operador: vale para os dois sentidos."""
    distancia = _decimal(distancia_km)
    if distancia is None or distancia <= 0:
        raise ValueError("Informe uma distância em km maior que zero.")
    registro = registrar(origem_id, destino_id, distancia, fonte=DistanciaMunicipios.Fonte.MANUAL)
    inverso = DistanciaMunicipios.objects.filter(origem_id=destino_id, destino_id=origem_id).first()
    if inverso is not None:
        registrar(destino_id, origem_id, distancia, fonte=DistanciaMunicipios.Fonte.MANUAL)
    return registro


def distancia_do_trecho(trecho):
    """Distância prevista de um trecho de roteiro, em km (Decimal) ou ``None``.

    A tabela vem primeiro (é onde vivem as correções manuais); sem ela, a
    distância gravada no próprio trecho — que passa a ficar guardada para os
    próximos roteiros e diários.
    """
    if trecho is None:
        return None
    registro = buscar(trecho.origem_municipio_id, trecho.destino_municipio_id)
    if registro is not None:
        return registro.distancia_km
    if trecho.distancia_km:
        registrar(
            trecho.origem_municipio_id,
            trecho.destino_municipio_id,
            trecho.distancia_km,
            fonte=DistanciaMunicipios.Fonte.ROTEIRO,
            duracao_min=trecho.duracao_min,
            tempo_viagem_min=trecho.tempo_viagem_min,
        )
        return trecho.distancia_km
    return None


def carregar_dos_roteiros():
    """Grava os pares dos trechos já existentes que ainda não estão na tabela.

    Não chama serviço externo e não mexe em pares já gravados. Devolve quantos criou.
    """
    from ..models import RoteiroTrecho

    criados = 0
    vistos = set()
    trechos = (
        RoteiroTrecho.objects.filter(
            origem_municipio__isnull=False,
            destino_municipio__isnull=False,
            distancia_km__gt=0,
        )
        .order_by("-atualizado_em")
        .values_list("origem_municipio_id", "destino_municipio_id", "distancia_km", "duracao_min", "tempo_viagem_min")
    )
    for origem_id, destino_id, distancia, duracao, viagem in trechos:
        if origem_id == destino_id or (origem_id, destino_id) in vistos:
            continue
        vistos.add((origem_id, destino_id))
        if buscar(origem_id, destino_id) is not None:
            continue
        registrar(
            origem_id,
            destino_id,
            distancia,
            fonte=DistanciaMunicipios.Fonte.ROTEIRO,
            duracao_min=duracao,
            tempo_viagem_min=viagem,
        )
        criados += 1
    return criados
