"""Limite de tentativas das páginas públicas (sem login), no cache do Django.

Usado pelo pedido de palestra (/pedido/) e pelo link do fornecedor do Coffee
Break (/fornecedor/): conta envios por chave (IP, token) numa janela e diz
quando passou do limite. Sem serviço externo; com vários processos, o cache
precisa ser compartilhado (arquivo, banco ou Redis) para o limite valer entre
eles.
"""

import hashlib

from django.conf import settings
from django.core.cache import cache


def ip_do_cliente(request):
    """O IP de quem envia. Atrás do proxy (nginx), só com o ajuste ligado o
    X-Forwarded-For vale — e dele o último endereço, o que o próprio proxy
    acrescentou; o resto do cabeçalho vem do cliente e pode ser forjado."""
    if getattr(settings, "PEDIDO_PUBLICO_CONFIAR_X_FORWARDED_FOR", False):
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ultimo = encaminhado.split(",")[-1].strip()
        if ultimo:
            return ultimo[:64]
    return (request.META.get("REMOTE_ADDR") or "desconhecido")[:64]


def _chave(escopo, valor):
    return f"limite:{escopo}:{hashlib.sha256(str(valor).encode()).hexdigest()}"


def contagem(escopo, valor):
    return cache.get(_chave(escopo, valor), 0)


def excedeu(escopo, valor, limite):
    return contagem(escopo, valor) >= limite


def somar(escopo, valor, janela):
    chave = _chave(escopo, valor)
    # add() só cria (com a janela como validade); incr() soma sem renovar.
    if not cache.add(chave, 1, janela):
        try:
            cache.incr(chave)
        except ValueError:
            cache.set(chave, 1, janela)


def cabecalhos_de_pagina_com_token(resposta):
    """Página cujo endereço carrega um token: o navegador não o repassa a
    outros sites (Referer) e buscadores não a indexam."""
    resposta["Referrer-Policy"] = "no-referrer"
    resposta["X-Robots-Tag"] = "noindex, nofollow"
    return resposta
