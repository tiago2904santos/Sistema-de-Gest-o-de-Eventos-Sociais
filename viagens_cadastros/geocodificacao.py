"""Coordenadas de municípios pela API Nominatim (OpenStreetMap).

Usado pelo comando `geocodificar_municipios` e, sob demanda, pelo cálculo de
rota quando um município do percurso ainda não tem coordenadas. O buscador de
endereço das telas de eventos (`core.buscar_endereco`) usa `buscar_enderecos`
para achar bairro, lugar ou rua pelo nome.
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


class MapaIndisponivel(Exception):
    """O Nominatim não respondeu (rede, timeout ou resposta estranha)."""


def buscar_enderecos(texto, limite=6, timeout=4):
    """Lugares do Nominatim para um texto livre, com o endereço em partes.

    Devolve a lista crua do Nominatim (`addressdetails=1`, só Brasil) — cada
    item com `name`, `addresstype` e `address` (road, suburb, city, postcode…).
    Quem chama respeita o limite de 1 requisição por segundo.
    """
    parametros = urllib.parse.urlencode(
        {
            "q": texto,
            "format": "jsonv2",
            "limit": limite,
            "countrycodes": "br",
            "addressdetails": 1,
            "accept-language": "pt-BR",
        }
    )
    pedido = urllib.request.Request(
        f"{NOMINATIM_URL}?{parametros}", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            resultados = json.load(resposta)
    except Exception as exc:
        raise MapaIndisponivel from exc
    if not isinstance(resultados, list):
        raise MapaIndisponivel
    return [item for item in resultados if isinstance(item, dict)]
