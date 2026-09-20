"""Configuração do canal, lida de `settings` ou do ambiente.

Nada aqui tem valor padrão que "funcione": sem credencial o canal fica
desligado e diz isso em voz alta. Um webhook que aceita qualquer POST porque
o segredo não foi configurado é pior que um webhook desligado.
"""

from __future__ import annotations

import os

from django.conf import settings

# Conversa de serviço (iniciada por quem escreve) é gratuita enquanto está
# aberta; fora dela só template aprovado, que é pago e exige aprovação prévia.
# Como este canal é só de entrada, sair da janela significa não responder.
JANELA_DE_SERVICO_HORAS = 24

URL_GRAPH = "https://graph.facebook.com/v21.0"

TIMEOUT_SEGUNDOS = 15


def _ler(nome: str, padrao: str = "") -> str:
    valor = getattr(settings, nome, None)
    if valor is None:
        valor = os.environ.get(nome, padrao)
    return (valor or "").strip()


def token() -> str:
    """Token de acesso da Cloud API, para responder e baixar áudio."""
    return _ler("WHATSAPP_TOKEN")


def phone_number_id() -> str:
    """Id do número emissor, na conta business."""
    return _ler("WHATSAPP_PHONE_NUMBER_ID")


def app_secret() -> str:
    """Segredo do app, usado para conferir a assinatura de cada POST."""
    return _ler("WHATSAPP_APP_SECRET")


def verify_token() -> str:
    """Segredo combinado no handshake de verificação do webhook."""
    return _ler("WHATSAPP_VERIFY_TOKEN")


def envio_configurado() -> bool:
    return bool(token() and phone_number_id())
