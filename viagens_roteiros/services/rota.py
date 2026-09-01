"""Cálculo de rota do percurso via OpenRouteService.

Espelha o contrato validado na Central de Viagens 3: o servidor chama a API
``/v2/directions/driving-car/geojson`` com as coordenadas dos municípios, e a
resposta volta como LineString (``[lng, lat]``, o que o Leaflet consome) mais
os totais e os segmentos ponto a ponto. A chave fica só no ``.env``
(``OPENROUTESERVICE_API_KEY``); o navegador nunca fala com a API.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"


class RotaIndisponivel(Exception):
    """Erro de rota com mensagem pronta para o operador."""


def _pontos_dos_municipios(municipios):
    pontos = []
    sem_coordenada = []
    for municipio in municipios:
        if municipio.latitude is None or municipio.longitude is None:
            sem_coordenada.append(str(municipio))
            continue
        pontos.append(
            {
                "id": municipio.pk,
                "nome": municipio.nome,
                "uf": municipio.estado.sigla,
                "lat": float(municipio.latitude),
                "lng": float(municipio.longitude),
            }
        )
    if sem_coordenada:
        nomes = ", ".join(dict.fromkeys(sem_coordenada))
        raise RotaIndisponivel(
            f"Sem coordenadas cadastradas para: {nomes}. "
            "Importe as coordenadas dos municípios para calcular a rota."
        )
    return pontos


def _chamar_ors(coordenadas):
    chave = (settings.OPENROUTESERVICE_API_KEY or "").strip()
    if not chave:
        raise RotaIndisponivel(
            "Cálculo de rota não configurado: defina OPENROUTESERVICE_API_KEY "
            "no .env do servidor."
        )
    corpo = json.dumps(
        {
            "coordinates": coordenadas,
            "preference": "recommended",
            "units": "m",
            "geometry": True,
        }
    ).encode("utf-8")
    pedido = urllib.request.Request(
        ORS_URL,
        data=corpo,
        headers={
            "Authorization": chave,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/geo+json, application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            pedido, timeout=settings.ROUTE_REQUEST_TIMEOUT_SECONDS
        ) as resposta:
            return json.load(resposta)
    except urllib.error.HTTPError as erro:
        logger.warning("OpenRouteService HTTP %s", erro.code)
        if erro.code in (401, 403):
            raise RotaIndisponivel(
                "A chave do OpenRouteService foi recusada. Confira o .env."
            ) from erro
        if erro.code == 429:
            raise RotaIndisponivel(
                "Limite de consultas de rota atingido. Tente em instantes."
            ) from erro
        raise RotaIndisponivel(
            "O serviço de rotas não conseguiu calcular este percurso."
        ) from erro
    except (urllib.error.URLError, TimeoutError) as erro:
        logger.warning("OpenRouteService indisponível: %s", erro)
        raise RotaIndisponivel(
            "Serviço de rotas fora do ar ou sem internet no servidor."
        ) from erro


def _minutos(segundos):
    return max(0, int(round(float(segundos or 0) / 60.0)))


def calcular_rota(municipios):
    """Rota pelo percurso, na ordem dada (sede, destinos…, sede).

    Devolve totais, os segmentos entre pontos consecutivos (para preencher a
    distância e o tempo de viagem de cada trecho) e a geometria para o mapa.
    """
    if len(municipios) < 2:
        raise RotaIndisponivel("Escolha a sede e ao menos um destino.")
    pontos = _pontos_dos_municipios(municipios)
    dados = _chamar_ors([[p["lng"], p["lat"]] for p in pontos])

    atributos = ((dados.get("features") or [{}])[0]) or {}
    propriedades = atributos.get("properties") or {}
    resumo = propriedades.get("summary") or {}
    if not resumo:
        raise RotaIndisponivel("O serviço de rotas não devolveu um resumo do percurso.")

    segmentos = []
    for indice, segmento in enumerate(propriedades.get("segments") or []):
        if indice >= len(pontos) - 1:
            break
        segmentos.append(
            {
                "de": pontos[indice]["id"],
                "para": pontos[indice + 1]["id"],
                "de_rotulo": f"{pontos[indice]['nome']}/{pontos[indice]['uf']}",
                "para_rotulo": f"{pontos[indice + 1]['nome']}/{pontos[indice + 1]['uf']}",
                "distancia_km": round(float(segmento.get("distance") or 0) / 1000.0, 2),
                "duracao_min": _minutos(segmento.get("duration")),
            }
        )

    geometria = atributos.get("geometry")
    if not (isinstance(geometria, dict) and geometria.get("type") == "LineString"):
        geometria = None

    return {
        "pontos": pontos,
        "segmentos": segmentos,
        "distancia_total_km": round(float(resumo.get("distance") or 0) / 1000.0, 2),
        "duracao_total_min": _minutos(resumo.get("duration")),
        "geometria": geometria,
    }
