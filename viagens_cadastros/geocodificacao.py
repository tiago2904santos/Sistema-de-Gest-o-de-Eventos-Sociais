"""Coordenadas de municípios pela API Nominatim (OpenStreetMap).

Usado pelo comando `geocodificar_municipios` e, sob demanda, pelo cálculo de
rota quando um município do percurso ainda não tem coordenadas.
"""

import json
import urllib.parse
import urllib.request

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "SistemaGestaoEventosSociais/1.0"
# Nominatim exige no máximo 1 requisição por segundo.
INTERVALO_SEGUNDOS = 1.1


def _buscar_coordenadas(nome, uf):
    parametros = urllib.parse.urlencode(
        {
            "q": f"{nome}, {uf}, Brasil",
            "format": "json",
            "limit": 1,
            "countrycodes": "br",
            "addressdetails": 0,
        }
    )
    pedido = urllib.request.Request(
        f"{NOMINATIM_URL}?{parametros}", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(pedido, timeout=15) as resposta:
            resultados = json.load(resposta)
    except Exception:
        return None
    if not resultados:
        return None
    try:
        return float(resultados[0]["lat"]), float(resultados[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def geocodificar(municipio):
    """Busca e grava as coordenadas de um município; devolve se conseguiu."""
    coordenadas = _buscar_coordenadas(municipio.nome, municipio.estado.sigla)
    if coordenadas is None:
        return False
    municipio.latitude, municipio.longitude = coordenadas
    type(municipio).objects.filter(pk=municipio.pk).update(
        latitude=municipio.latitude, longitude=municipio.longitude
    )
    return True
