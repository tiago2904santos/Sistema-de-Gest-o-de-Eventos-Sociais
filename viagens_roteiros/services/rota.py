"""Cálculo de rota do percurso via OpenRouteService.

Espelha o contrato validado na Central de Viagens 3: o servidor chama a API
``/v2/directions/driving-car/geojson`` com as coordenadas dos municípios, e a
resposta volta como LineString (``[lng, lat]``, o que o Leaflet consome) mais
os totais e os segmentos ponto a ponto. A chave fica só no ``.env``
(``OPENROUTESERVICE_API_KEY``); o navegador nunca fala com a API.
"""

import hashlib
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
FONTE = "openrouteservice"

# Regras de tempo do editor de referência, para os tempos de viagem saírem
# iguais aos que a Central de Viagens estimava para os mesmos trechos:
#
# - a ETA vem de uma velocidade média calibrada (74 km/h) sobre a distância
#   rodoviária mais 12 km de "custo fixo" (sair e entrar na cidade), com a
#   duração devolvida pela API pesando 15% — ela tende a ser otimista;
# - o resultado é arredondado a passos de 15 minutos (resto de até 5 minutos
#   cai para baixo, acima disso sobe);
# - o tempo adicional sugerido é 1/6 da viagem, nunca menor que 15 minutos,
#   e zero em viagens de menos de meia hora.
VELOCIDADE_MEDIA_KMH = 74.0
DISTANCIA_FIXA_KM = 12.0
PESO_DA_API = 0.15
PASSO_MIN = 15
VIAGEM_MINIMA_PARA_ADICIONAL_MIN = 30
CACHE_ESTIMATIVA_SEGUNDOS = 60 * 60 * 24


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


def arredondar_a_15(minutos):
    """Passos de 15 minutos: até 5 de resto cai, acima sobe."""
    minutos = max(0, int(round(minutos)))
    resto = minutos % PASSO_MIN
    base = minutos - resto
    return base if resto <= 5 else base + PASSO_MIN


def tempo_de_viagem(distancia_km, duracao_api_min):
    """Tempo de viagem calibrado, em minutos, a partir da distância e da API."""
    calibrado = (float(distancia_km) + DISTANCIA_FIXA_KM) / VELOCIDADE_MEDIA_KMH * 60.0
    combinado = (1 - PESO_DA_API) * calibrado + PESO_DA_API * float(duracao_api_min or 0)
    return arredondar_a_15(combinado)


def tempo_adicional_sugerido(tempo_viagem_min):
    if tempo_viagem_min < VIAGEM_MINIMA_PARA_ADICIONAL_MIN:
        return 0
    return max(PASSO_MIN, arredondar_a_15(tempo_viagem_min / 6.0))


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
        distancia_km = round(float(segmento.get("distance") or 0) / 1000.0, 2)
        duracao_api = _minutos(segmento.get("duration"))
        viagem = tempo_de_viagem(distancia_km, duracao_api)
        segmentos.append(
            {
                "de": pontos[indice]["id"],
                "para": pontos[indice + 1]["id"],
                "de_rotulo": f"{pontos[indice]['nome']}/{pontos[indice]['uf']}",
                "para_rotulo": f"{pontos[indice + 1]['nome']}/{pontos[indice + 1]['uf']}",
                "distancia_km": distancia_km,
                "duracao_min": duracao_api,
                "tempo_viagem_min": viagem,
                "tempo_adicional_sugerido_min": tempo_adicional_sugerido(viagem),
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
        "fonte": FONTE,
        "calculada_em": timezone.now().isoformat(),
        "assinatura": assinatura_dos_ids([p["id"] for p in pontos]),
    }


def estimar_trecho(origem, destino):
    """Distância e tempo de viagem entre dois municípios, sem desenho.

    É o que preenche os trechos assim que sede e destinos existem, antes de
    qualquer "Calcular rota" — como no editor de referência. O par é guardado
    em cache por um dia: o mesmo trecho aparece em roteiros diferentes e a
    resposta da API não muda de um minuto para o outro.
    """
    chave = f"viagens:estimativa:{origem.pk}:{destino.pk}"
    guardado = cache.get(chave)
    if guardado:
        return guardado
    pontos = _pontos_dos_municipios([origem, destino])
    dados = _chamar_ors([[p["lng"], p["lat"]] for p in pontos])
    atributos = ((dados.get("features") or [{}])[0]) or {}
    resumo = (atributos.get("properties") or {}).get("summary") or {}
    if not resumo:
        raise RotaIndisponivel("O serviço de rotas não devolveu um resumo do trecho.")
    distancia_km = round(float(resumo.get("distance") or 0) / 1000.0, 2)
    duracao_api = _minutos(resumo.get("duration"))
    viagem = tempo_de_viagem(distancia_km, duracao_api)
    resultado = {
        "origem": pontos[0]["id"],
        "destino": pontos[1]["id"],
        "distancia_km": distancia_km,
        "duracao_min": duracao_api,
        "tempo_viagem_min": viagem,
        "tempo_adicional_sugerido_min": tempo_adicional_sugerido(viagem),
        "fonte": FONTE,
    }
    cache.set(chave, resultado, CACHE_ESTIMATIVA_SEGUNDOS)
    return resultado


# ---------------------------------------------------------------------------
# Rota gravada no roteiro
# ---------------------------------------------------------------------------


def assinatura_dos_ids(ids):
    """Identifica um percurso: os municípios na ordem, e nada mais."""
    texto = ">".join(str(i) for i in ids if i)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest() if texto else ""


def assinatura_do_percurso(roteiro):
    """A assinatura do que está gravado: sede, destinos na ordem, sede."""
    ids = [roteiro.origem_municipio_id]
    ids += [d.municipio_id for d in roteiro.destinos.order_by("ordem", "pk")]
    if len(ids) > 1:
        ids.append(roteiro.origem_municipio_id)
    return assinatura_dos_ids(ids)


def _decimal(valor):
    if valor in ("", None):
        return None
    try:
        return Decimal(str(valor).replace(",", "."))
    except InvalidOperation:
        return None


def _inteiro(valor):
    try:
        return max(0, int(float(valor)))
    except (TypeError, ValueError):
        return None


def _instante(valor):
    if not valor:
        return timezone.now()
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return timezone.now()
    if timezone.is_naive(instante):
        instante = timezone.make_aware(instante)
    return instante


def aplicar_rota_enviada(roteiro, dados):
    """Grava no roteiro a rota que a tela calculou, se ela vier inteira.

    A tela guarda a última rota em campos ocultos e a manda junto com o
    formulário. Só uma LineString com coordenadas conta; qualquer outra coisa
    (vazio, JSON quebrado) é ignorada em silêncio — o roteiro salva do mesmo
    jeito, só sem rota.
    """
    bruto = (dados.get("rota_geojson") or "").strip()
    if not bruto:
        return False
    try:
        geometria = json.loads(bruto)
    except ValueError:
        return False
    if not (
        isinstance(geometria, dict)
        and geometria.get("type") == "LineString"
        and geometria.get("coordinates")
    ):
        return False
    roteiro.rota_geojson = geometria
    roteiro.rota_distancia_km = _decimal(dados.get("rota_distancia_km"))
    roteiro.rota_duracao_min = _inteiro(dados.get("rota_duracao_min"))
    roteiro.rota_fonte = (dados.get("rota_fonte") or FONTE)[:40]
    roteiro.rota_assinatura = (dados.get("rota_assinatura") or "")[:128]
    roteiro.rota_calculada_em = _instante(dados.get("rota_calculada_em"))
    roteiro.rota_status = roteiro.RotaStatus.CALCULADA
    return True


def conferir_rota_gravada(roteiro):
    """Depois de gravar o percurso: a rota ainda o descreve?

    Se sede ou destinos mudaram desde o cálculo, a rota fica marcada como
    desatualizada — continua desenhada, mas a tela pede o recálculo. O
    inverso também vale: se o percurso voltou ao que a rota descreve, ela
    volta a valer.
    """
    if not roteiro.rota_geojson:
        return
    atual = assinatura_do_percurso(roteiro)
    if roteiro.rota_assinatura and atual == roteiro.rota_assinatura:
        novo = roteiro.RotaStatus.CALCULADA
    else:
        novo = roteiro.RotaStatus.DESATUALIZADA
    if novo != roteiro.rota_status:
        roteiro.rota_status = novo
        roteiro.save(update_fields=["rota_status", "atualizado_em"])


def rota_para_tela(roteiro):
    """A rota gravada no formato que o mapa da tela consome."""
    if not roteiro or not roteiro.pk or not roteiro.rota_geojson:
        return None
    municipios = [roteiro.origem_municipio] if roteiro.origem_municipio_id else []
    municipios += [
        d.municipio for d in roteiro.destinos.select_related("municipio__estado")
    ]
    if len(municipios) > 1:
        municipios.append(municipios[0])
    pontos = []
    for municipio in municipios:
        if municipio.latitude is None or municipio.longitude is None:
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
    return {
        "status": roteiro.rota_status,
        "geometria": roteiro.rota_geojson,
        "pontos": pontos,
        "distancia_total_km": (
            float(roteiro.rota_distancia_km)
            if roteiro.rota_distancia_km is not None
            else None
        ),
        "duracao_total_min": roteiro.rota_duracao_min,
        "fonte": roteiro.rota_fonte,
        "assinatura": roteiro.rota_assinatura,
        "calculada_em": (
            roteiro.rota_calculada_em.isoformat() if roteiro.rota_calculada_em else ""
        ),
    }
