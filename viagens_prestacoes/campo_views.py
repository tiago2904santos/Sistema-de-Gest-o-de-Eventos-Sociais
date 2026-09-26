"""A página do diário de bordo no celular do motorista (m096) — sem login.

Rotas em `campo_urls.py`, fora do namespace do módulo: o middleware de módulos
não as cobre, e quem abre é o motorista, com o link. O link é a credencial e só
alcança aquele diário; tudo o mais do sistema continua exigindo login.

O envio (`sincronizar`) não usa sessão nem cookie, então o token CSRF do Django
não se aplica — no lugar dele: o token do link no caminho, corpo só em
`application/json` com o cabeçalho `X-Diario-Campo` (um formulário de outro site
não consegue mandar nenhum dos dois sem um preflight que este servidor não
responde), `Origin` do próprio sistema quando o navegador o envia, limite de
tamanho e de taxa.
"""

from __future__ import annotations

import json

from django.core.cache import cache
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST

from .campo_services import EnvioInvalido
from .campo_services import LinkInvalido
from .campo_services import aplicar_lancamentos
from .campo_services import dados_da_pagina
from .campo_services import diario_travado
from .campo_services import estado_do_diario
from .campo_services import obter_link_valido
from .models import LinkDiarioCampo

#: Maior corpo aceito no envio: 50 lançamentos cabem com folga em 32 KB.
TAMANHO_MAXIMO_ENVIO = 32 * 1024
#: Envios por minuto: por link e por endereço. A fila do celular manda em lotes,
#: então isto só barra abuso.
LIMITE_POR_LINK = 30
LIMITE_POR_IP = 120
JANELA_SEGUNDOS = 60


def _cabecalhos_privados(resposta):
    # O token está no caminho: nada de mandá-lo como Referer para outro site,
    # nem de indexar a página.
    resposta["Referrer-Policy"] = "no-referrer"
    resposta["X-Robots-Tag"] = "noindex, nofollow"
    resposta["Cache-Control"] = "private, no-cache"
    return resposta


def _estourou(chave: str, limite: int) -> bool:
    chave = f"diario-campo:{chave}"
    if cache.add(chave, 1, JANELA_SEGUNDOS):
        return False
    try:
        return cache.incr(chave) > limite
    except ValueError:  # expirou entre o add e o incr
        cache.add(chave, 1, JANELA_SEGUNDOS)
        return False


def _ip(request) -> str:
    return request.META.get("REMOTE_ADDR", "") or "?"


def _erro(mensagem, status, **extra):
    return _cabecalhos_privados(JsonResponse({"ok": False, "mensagem": mensagem, **extra}, status=status))


@require_GET
def pagina(request, token):
    try:
        link = obter_link_valido(token)
    except LinkInvalido as exc:
        status = 404 if exc.motivo == "inexistente" else 410
        resposta = render(request, "pages/campo/link_invalido.html", {"mensagem": str(exc)}, status=status)
        return _cabecalhos_privados(resposta)
    LinkDiarioCampo.objects.filter(pk=link.pk).update(ultimo_acesso_em=timezone.now())
    contexto = {
        "dados": dados_da_pagina(link),
        "token": link.token,
        "url_enviar": reverse("campo_diario:enviar", args=[link.token]),
        "url_manifest": reverse("campo_diario:manifest", args=[link.token]),
        "url_sw": reverse("campo_diario:sw"),
    }
    return _cabecalhos_privados(render(request, "pages/campo/diario.html", contexto))


def _origem_permitida(request) -> bool:
    origem = request.headers.get("Origin")
    if not origem:
        return True  # navegadores antigos não mandam em POST do mesmo site
    return origem == f"{request.scheme}://{request.get_host()}"


@csrf_exempt
@require_POST
def sincronizar(request, token):
    if request.headers.get("X-Diario-Campo") != "1" or request.content_type != "application/json":
        return _erro("Envio fora do formato do diário.", 400)
    if not _origem_permitida(request):
        return _erro("Origem não permitida.", 403)
    try:
        tamanho = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        tamanho = 0
    if tamanho > TAMANHO_MAXIMO_ENVIO:
        return _erro("Envio grande demais.", 413)
    if _estourou(f"ip:{_ip(request)}", LIMITE_POR_IP) or _estourou(f"link:{str(token)[:64]}", LIMITE_POR_LINK):
        resposta = _erro("Muitos envios seguidos. Tente de novo em um minuto.", 429)
        resposta["Retry-After"] = str(JANELA_SEGUNDOS)
        return resposta
    try:
        link = obter_link_valido(token)
    except LinkInvalido as exc:
        return _erro(str(exc), 404 if exc.motivo == "inexistente" else 410, motivo=exc.motivo)
    corpo = request.read(TAMANHO_MAXIMO_ENVIO + 1)
    if len(corpo) > TAMANHO_MAXIMO_ENVIO:
        return _erro("Envio grande demais.", 413)
    try:
        payload = json.loads(corpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _erro("Envio ilegível.", 400)
    if not isinstance(payload, dict):
        return _erro("Envio fora do formato do diário.", 400)
    if diario_travado(link.diario):
        return _erro("A prestação de contas desta viagem já foi finalizada; o diário não aceita mais alterações.", 409, motivo="travado")
    try:
        resultados = aplicar_lancamentos(link, payload.get("lancamentos"))
    except EnvioInvalido as exc:
        return _erro(str(exc), 400)
    return _cabecalhos_privados(JsonResponse({"ok": True, "resultados": resultados, "estado": estado_do_diario(link.diario)}))


@require_GET
def manifest(request, token):
    """Manifesto do app instalável: abre direto no diário deste link."""
    try:
        link = obter_link_valido(token)
    except LinkInvalido:
        return HttpResponse(status=404)
    inicio = reverse("campo_diario:pagina", args=[link.token])
    dados = {
        "name": "Diário de bordo",
        "short_name": "Diário",
        "start_url": inicio,
        "scope": inicio,
        "display": "standalone",
        "background_color": "#fafafa",
        "theme_color": "#333333",
        "icons": [{"src": static("icons/favicon.svg"), "sizes": "any", "type": "image/svg+xml"}],
    }
    resposta = JsonResponse(dados, content_type="application/manifest+json")
    return _cabecalhos_privados(resposta)


@require_GET
def service_worker(request):
    """O service worker das páginas do diário: guarda a página e os arquivos para abrir sem internet."""
    resposta = HttpResponse(render_to_string("pages/campo/sw.js"), content_type="application/javascript; charset=utf-8")
    resposta["Cache-Control"] = "no-cache"
    resposta["Service-Worker-Allowed"] = reverse("campo_diario:sw").rsplit("/", 1)[0] + "/"
    return resposta
