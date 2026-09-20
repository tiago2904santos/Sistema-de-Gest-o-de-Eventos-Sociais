"""O webhook. Duas responsabilidades, e nenhuma a mais.

`GET` é o handshake que a Meta faz ao cadastrar a URL. `POST` é a entrega de
mensagem: confere a assinatura, grava e responde 200 — **sem processar nada**.

Por que não processar aqui: a Meta espera resposta em segundos e reentrega o
que não confirmou. Transcrever um áudio dentro do request estouraria o prazo
e a mesma fala viraria duas viagens. O trabalho é do comando
`processar_whatsapp`.

A rota é anônima por necessidade — quem chama é a Meta, não uma pessoa
logada. Quem faz o papel da autenticação é a assinatura HMAC; por isso ela é
conferida antes de qualquer outra coisa e recusa quando não há segredo.

O namespace `assistente_whatsapp` fica fora do catálogo de módulos de
propósito: o middleware de autorização bloquearia a URL, e a Meta não tem
como se autenticar como usuário de um setor.
"""

from __future__ import annotations

import hmac
import json
import logging

from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import config
from .assinatura import CABECALHO, AssinaturaInvalida, conferir
from .payload import extrair
from .servico import registrar_entradas

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    if request.method == "GET":
        return _verificacao(request)
    return _entrega(request)


def _verificacao(request):
    """Handshake de cadastro: devolve o desafio quando o token combina."""
    esperado = config.verify_token()
    if not esperado:
        logger.error("WHATSAPP_VERIFY_TOKEN não configurado.")
        return HttpResponseForbidden("Webhook não configurado.")

    recebido = request.GET.get("hub.verify_token") or ""
    desafio = request.GET.get("hub.challenge") or ""
    if request.GET.get("hub.mode") != "subscribe" or not hmac.compare_digest(
        esperado, recebido
    ):
        logger.warning("Handshake recusado.")
        return HttpResponseForbidden("Token de verificação inválido.")
    # A Meta exige o desafio de volta em texto puro, sem aspas nem JSON.
    return HttpResponse(desafio, content_type="text/plain")


def _entrega(request):
    try:
        conferir(request.body, request.META.get(CABECALHO))
    except AssinaturaInvalida as erro:
        logger.warning("POST recusado no webhook: %s", erro)
        return HttpResponseForbidden("Assinatura inválida.")

    try:
        corpo = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Assinatura válida e corpo ilegível não se resolve com reentrega.
        logger.warning("Corpo do webhook não é JSON válido.")
        return JsonResponse({"recebidas": 0})

    gravadas = registrar_entradas(extrair(corpo))
    return JsonResponse({"recebidas": len(gravadas)})
