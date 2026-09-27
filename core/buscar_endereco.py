"""Buscador de endereço das telas de eventos (Endereço/Bairro/CEP).

A pessoa digita o nome de uma rua, de um bairro ou de um lugar ("Rua XV de
Novembro", "Uvaranas", "Ginásio Municipal") — ou um CEP — e a tela mostra
sugestões; a escolhida preenche endereço, bairro, CEP e o município
(`static/js/buscar-endereco.js`, no componente `endereco_campos.html`).

Fontes, nesta ordem, juntas e sem repetir:

1. ``cadastro`` — endereços já usados no sistema (solicitações de evento,
   coffee breaks e palestras), filtrados pelo município da tela. Rápido e
   sem sair do servidor.
2. ``cep`` — ViaCEP: pelo CEP (8 dígitos) ou pelo nome da rua na cidade da
   tela (o ViaCEP exige UF, cidade e ao menos 3 letras).
3. ``mapa`` — Nominatim (OpenStreetMap), para bairro, lugar ou rua quando o
   ViaCEP não achou nada.

As chamadas externas saem só daqui (nunca do navegador), com timeout curto,
cache de um dia por consulta e limite por usuário. Para fora vai só o texto
do endereço e a cidade/UF — nenhum dado da pessoa ou do evento. Se o serviço
não responde, a tela mostra só as sugestões do cadastro e avisa.
"""

from __future__ import annotations

import hashlib
import re
import time

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from cadastros.models import Estado, Municipio
from core import limite
from core.normalizers import remove_accents
from viagens_cadastros import geocodificacao
from viagens_cadastros.cep import CEPIndisponivel, CEPNaoEncontrado, consultar_cep, consultar_logradouro

#: Menor texto que dispara a busca (o ViaCEP pede 3 letras da rua).
MINIMO_LETRAS = 3
#: Timeout das chamadas externas, em segundos.
TIMEOUT_EXTERNO = 4
#: Validade do cache de cada consulta externa (um dia).
CACHE_SEGUNDOS = 24 * 60 * 60
#: Consultas externas (fora do cache) por usuário numa janela.
LIMITE_POR_USUARIO = 30
JANELA_LIMITE_SEGUNDOS = 60
#: Quantas sugestões de cada fonte e no total.
MAXIMO_CADASTRO = 6
MAXIMO_EXTERNO = 6
MAXIMO_TOTAL = 12
#: Registros recentes de cada módulo em que a busca local procura.
REGISTROS_LOCAIS = 800

AVISO_FORA = "Sem resposta do serviço de CEP/mapa — mostrando só os endereços já cadastrados."
AVISO_LIMITE = "Muitas buscas seguidas — por um minuto, só os endereços já cadastrados."

_CEP = re.compile(r"^\s*(\d{5})-?(\d{3})\s*$")
# Número no fim do texto ("Rua XV de Novembro, 500" ou "... 500"), mas não o
# número de rodovia ("BR 376", "PR-151").
_NUMERO_FINAL = re.compile(r"^(?P<rua>.*?[^\W\d_].*?)(?:\s*,\s*|\s+)(?P<numero>\d{1,5}[A-Za-z]?|s/?n)\s*$", re.I)
_RODOVIA = re.compile(r"\b[A-Z]{2}\s*-?\s*$")
# Endereço gravado: "Rua das Flores, 123, sala 2" → rua e "123, sala 2".
_NUMERO_GRAVADO = re.compile(r"^(?P<rua>[^,]+?)\s*,\s*(?P<numero>(?:\d|s/?n\b|km\b).*)$", re.I)


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e com espaços simples — para comparar nomes."""
    return " ".join(remove_accents(texto or "").lower().split())


def separar_numero(texto: str) -> tuple[str, str]:
    """Separa o número que veio no fim da busca: ("Rua X", "500")."""
    texto = " ".join((texto or "").split())
    achado = _NUMERO_FINAL.match(texto)
    if not achado or _RODOVIA.search(achado.group("rua")):
        return texto, ""
    return achado.group("rua").rstrip(" ,"), achado.group("numero")


def separar_numero_gravado(endereco: str) -> tuple[str, str]:
    """O endereço gravado em rua e resto ("123, sala 2")."""
    endereco = " ".join((endereco or "").split())
    achado = _NUMERO_GRAVADO.match(endereco)
    if not achado:
        return endereco, ""
    return achado.group("rua"), achado.group("numero")


def formatar_cep(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    return f"{digitos[:5]}-{digitos[5:]}" if len(digitos) == 8 else ""


# --- Município ---------------------------------------------------------------


def _mapa_municipios(uf: str) -> dict[str, tuple[int, str, int]]:
    """{nome normalizado: (pk, nome, pk do estado)} dos municípios da UF."""
    chave = f"buscar_endereco:municipios:{uf}"
    mapa = cache.get(chave)
    if mapa is None:
        mapa = {
            normalizar(nome): (pk, nome, estado_id)
            for pk, nome, estado_id in Municipio.objects.filter(estado__sigla=uf).values_list(
                "pk", "nome", "estado_id"
            )
        }
        cache.set(chave, mapa, 60 * 60)
    return mapa


def municipio_do_cadastro(cidade: str, uf: str):
    """O `Municipio` (pk, nome, pk do estado) pelo nome sem acento + UF."""
    uf = (uf or "").strip().upper()
    if not cidade or len(uf) != 2:
        return None
    return _mapa_municipios(uf).get(normalizar(cidade))


def _uf_de_iso(codigo: str) -> str:
    # O Nominatim diz o estado como "BR-PR" em ISO3166-2-lvl4.
    codigo = (codigo or "").upper()
    return codigo[3:] if codigo.startswith("BR-") and len(codigo) == 5 else ""


# --- Sugestões ---------------------------------------------------------------


def _sugestao(*, logradouro="", numero="", bairro="", cep="", municipio=None, cidade="", uf="", local="", fonte):
    """Uma sugestão no formato do JSON, com o município do cadastro quando há."""
    municipio_id = estado_id = None
    municipio_nome = cidade
    if municipio is not None:
        municipio_id, municipio_nome, estado_id = municipio
    rotulo = ", ".join(parte for parte in (logradouro, numero) if parte)
    detalhes = [parte for parte in (bairro, municipio_nome and f"{municipio_nome}{'/' + uf if uf else ''}", formatar_cep(cep)) if parte]
    if local and normalizar(local) != normalizar(logradouro):
        rotulo = f"{local} — {rotulo}" if rotulo else local
    if not rotulo:
        rotulo = bairro or municipio_nome
        detalhes = [parte for parte in detalhes if parte != bairro]
    return {
        "logradouro": logradouro,
        "numero": numero,
        "bairro": bairro,
        "cep": formatar_cep(cep),
        "municipio_id": municipio_id,
        "municipio_nome": municipio_nome,
        "estado_id": estado_id,
        "uf": uf,
        "local": local,
        "fonte": fonte,
        "rotulo": rotulo,
        "detalhe": " · ".join(detalhes),
    }


def _chave_unica(sugestao: dict) -> tuple:
    return (
        normalizar(sugestao["logradouro"]),
        normalizar(sugestao["bairro"]),
        sugestao["municipio_id"] or normalizar(sugestao["municipio_nome"]),
    )


def sugestoes_do_cadastro(consulta: str, municipio: Municipio | None) -> list[dict]:
    """Endereços já usados nos três módulos que casam com o texto digitado."""
    from coffee_break.models import SolicitacaoCoffeeBreak
    from demandas_eventos.models import DemandaEvento
    from solicitacoes.models import SolicitacaoEvento

    palavras = normalizar(consulta).split()
    digitos = re.sub(r"\D", "", consulta)
    if not palavras:
        return []
    fontes = (
        (SolicitacaoEvento, "local_evento"),
        (SolicitacaoCoffeeBreak, "local_entrega"),
        (DemandaEvento, "local"),
    )
    achados: dict[tuple, dict] = {}
    for modelo, campo_local in fontes:
        registros = modelo.objects.exclude(endereco="", bairro="", cep="")
        if municipio is not None:
            registros = registros.filter(municipio=municipio)
        linhas = registros.order_by("-pk").values_list(
            "endereco", "bairro", "cep", campo_local,
            "municipio_id", "municipio__nome", "municipio__estado_id", "municipio__estado__sigla",
        )[:REGISTROS_LOCAIS]
        for endereco, bairro, cep, local, mun_id, mun_nome, estado_id, uf in linhas:
            texto = normalizar(" ".join((local or "", endereco or "", bairro or "", cep or "")))
            casa_cep = len(digitos) == 8 and re.sub(r"\D", "", cep or "") == digitos
            if not casa_cep and not all(palavra in texto for palavra in palavras):
                continue
            rua, numero = separar_numero_gravado(endereco)
            sugestao = _sugestao(
                logradouro=rua, numero=numero, bairro=(bairro or "").strip(), cep=cep,
                municipio=(mun_id, mun_nome, estado_id) if mun_id else None,
                uf=uf or "", local=(local or "").strip(), fonte="cadastro",
            )
            chave = _chave_unica(sugestao) + (normalizar(sugestao["local"]),)
            if chave in achados:
                achados[chave]["_usos"] += 1
            else:
                sugestao["_usos"] = 1
                achados[chave] = sugestao
    resultado = sorted(achados.values(), key=lambda s: -s["_usos"])[:MAXIMO_CADASTRO]
    for sugestao in resultado:
        sugestao.pop("_usos")
    return resultado


def _do_viacep(item: dict, numero: str) -> dict:
    return _sugestao(
        logradouro=item.get("logradouro", ""), numero=numero, bairro=item.get("bairro", ""),
        cep=item.get("cep", ""), municipio=municipio_do_cadastro(item.get("cidade", ""), item.get("uf", "")),
        cidade=item.get("cidade", ""), uf=item.get("uf", ""), fonte="cep",
    )


def _do_nominatim(item: dict, numero: str) -> dict | None:
    endereco = item.get("address") or {}
    uf = _uf_de_iso(endereco.get("ISO3166-2-lvl4", ""))
    cidade = endereco.get("city") or endereco.get("town") or endereco.get("village") or endereco.get("municipality") or ""
    bairro = (
        endereco.get("suburb") or endereco.get("neighbourhood")
        or endereco.get("city_district") or endereco.get("quarter") or ""
    )
    rua = endereco.get("road") or ""
    nome = (item.get("name") or "").strip()
    tipo = item.get("addresstype") or ""
    if tipo in {"suburb", "neighbourhood", "city_district", "quarter"} and nome:
        bairro = bairro or nome
        nome = ""
    elif tipo == "road" or normalizar(nome) == normalizar(rua):
        nome = ""
    elif tipo in {"city", "town", "village", "municipality", "state", "country"}:
        return None  # a cidade inteira não é um endereço
    if not (rua or bairro or nome):
        return None
    return _sugestao(
        logradouro=rua, numero=numero if rua else "", bairro=bairro, cep=endereco.get("postcode", ""),
        municipio=municipio_do_cadastro(cidade, uf), cidade=cidade, uf=uf, local=nome, fonte="mapa",
    )


# --- Chamadas externas (com cache) -------------------------------------------


class _Fora(Exception):
    """O serviço externo não respondeu."""


class _Limite(Exception):
    """O usuário passou do limite de consultas externas."""


def _consultar(fonte: str, partes: tuple, funcao, usuario_id):
    """Resultado do cache ou da chamada externa (que conta no limite)."""
    chave = "buscar_endereco:" + fonte + ":" + hashlib.sha256(
        "|".join(normalizar(str(p)) for p in partes).encode()
    ).hexdigest()
    guardado = cache.get(chave)
    if guardado is not None:
        return guardado
    if limite.excedeu("buscar_endereco", usuario_id, LIMITE_POR_USUARIO):
        raise _Limite
    limite.somar("buscar_endereco", usuario_id, JANELA_LIMITE_SEGUNDOS)
    resultado = funcao()
    cache.set(chave, resultado, CACHE_SEGUNDOS)
    return resultado


def _cep(cep):
    try:
        dados = consultar_cep(cep, timeout=TIMEOUT_EXTERNO)
    except CEPNaoEncontrado:
        return []
    except CEPIndisponivel as exc:
        raise _Fora from exc
    return [{k: dados.get(k, "") for k in ("cep", "logradouro", "bairro", "cidade", "uf")}]


def _logradouro(uf, cidade, rua):
    try:
        return consultar_logradouro(uf, cidade, rua, timeout=TIMEOUT_EXTERNO)
    except CEPIndisponivel as exc:
        raise _Fora from exc


def _esperar_vez_do_nominatim():
    # O Nominatim pede no máximo 1 requisição por segundo (para o servidor todo).
    agora = time.time()
    ultimo = cache.get("buscar_endereco:nominatim:ultimo")
    if ultimo is not None and 0 <= agora - ultimo < geocodificacao.INTERVALO_SEGUNDOS:
        time.sleep(geocodificacao.INTERVALO_SEGUNDOS - (agora - ultimo))
    cache.set("buscar_endereco:nominatim:ultimo", time.time(), 10)


def _mapa(texto):
    _esperar_vez_do_nominatim()
    try:
        return geocodificacao.buscar_enderecos(texto, limite=MAXIMO_EXTERNO, timeout=TIMEOUT_EXTERNO)
    except geocodificacao.MapaIndisponivel as exc:
        raise _Fora from exc


def sugestoes_externas(consulta: str, municipio: Municipio | None, uf: str, usuario_id) -> tuple[list[dict], list[str]]:
    """Sugestões do ViaCEP e, se ele não achar, do Nominatim; e os avisos."""
    avisos: list[str] = []
    rua, numero = separar_numero(consulta)
    cidade = municipio.nome if municipio else ""
    uf = municipio.estado.sigla if municipio else uf
    resultados: list[dict] = []
    fora = False
    try:
        achado_cep = _CEP.match(consulta)
        if achado_cep:
            cep = achado_cep.group(1) + achado_cep.group(2)
            itens = _consultar("cep", (cep,), lambda: _cep(cep), usuario_id)
            return [_do_viacep(item, "") for item in itens], avisos
        if cidade and uf and len(rua) >= MINIMO_LETRAS:
            try:
                itens = _consultar("rua", (uf, cidade, rua), lambda: _logradouro(uf, cidade, rua), usuario_id)
                resultados = [_do_viacep(item, numero) for item in itens[:MAXIMO_EXTERNO]]
            except _Fora:
                fora = True
        if not resultados:
            texto = ", ".join(parte for parte in (rua, cidade, uf, "Brasil") if parte)
            try:
                itens = _consultar("mapa", (texto,), lambda: _mapa(texto), usuario_id)
                resultados = [s for s in (_do_nominatim(item, numero) for item in itens) if s]
                if municipio is not None:
                    # Com a cidade escolhida, o mapa não sugere outra cidade.
                    resultados = [s for s in resultados if s["municipio_id"] in (None, municipio.pk)]
                fora = False if resultados else fora
            except _Fora:
                fora = True
    except _Limite:
        avisos.append(AVISO_LIMITE)
        return resultados, avisos
    except _Fora:
        fora = True
    if fora and not resultados:
        avisos.append(AVISO_FORA)
    return resultados, avisos


def buscar(consulta: str, municipio: Municipio | None = None, uf: str = "", usuario_id=None) -> dict:
    """Sugestões das três fontes, juntas e sem repetir."""
    consulta = " ".join((consulta or "").split())[:120]
    if len(re.sub(r"\W", "", consulta)) < MINIMO_LETRAS:
        return {"resultados": [], "avisos": []}
    locais = sugestoes_do_cadastro(separar_numero(consulta)[0], municipio)
    externos, avisos = sugestoes_externas(consulta, municipio, uf, usuario_id)
    vistos = {_chave_unica(s) for s in locais}
    resultados = list(locais)
    for sugestao in externos:
        chave = _chave_unica(sugestao)
        # Mesmo lugar do cadastro: fica o do cadastro (tem o nome do local).
        if chave in vistos:
            continue
        vistos.add(chave)
        resultados.append(sugestao)
    return {"resultados": resultados[:MAXIMO_TOTAL], "avisos": avisos}


def _uf_da_requisicao(valor: str) -> str:
    """`uf` pode vir como sigla ("PR") ou como a pk do estado do select."""
    valor = (valor or "").strip()
    if valor.isdigit():
        return Estado.objects.filter(pk=int(valor)).values_list("sigla", flat=True).first() or ""
    return valor.upper() if len(valor) == 2 and valor.isalpha() else ""


@login_required
@require_GET
def buscar_endereco(request):
    """GET ?q=&municipio=<pk>&uf=<sigla ou pk do estado> → {"resultados", "avisos"}."""
    municipio = None
    municipio_pk = (request.GET.get("municipio") or "").strip()
    if municipio_pk.isdigit():
        municipio = Municipio.objects.select_related("estado").filter(pk=int(municipio_pk)).first()
    uf = _uf_da_requisicao(request.GET.get("uf", ""))
    dados = buscar(request.GET.get("q", ""), municipio=municipio, uf=uf, usuario_id=request.user.pk)
    return JsonResponse(dados)
