"""Conferência da assinatura do webhook — e a decisão de falhar fechado.

A Meta assina cada POST com HMAC-SHA256 do **corpo cru** usando o segredo do
app. Sem essa conferência, a URL do webhook é um endereço público que aceita
qualquer JSON: alguém que descubra o caminho manda "faça os documentos" em
nome de um número vinculado e o sistema obedece.

Duas escolhas que não são óbvias:

**Sem segredo configurado, recusa.** A tentação é "se não há segredo, aceita",
para facilitar o desenvolvimento. Isso é exatamente como um webhook chega
aberto em produção — basta a variável não ter sido copiada para o `.env` do
servidor. Um canal desligado é um problema visível; um canal aberto, não.

**Comparação em tempo constante.** `compare_digest` em vez de `==`: comparar
assinatura byte a byte com saída antecipada vaza, pelo tempo de resposta,
quantos bytes iniciais estavam certos.

O corpo precisa ser o **byte a byte recebido**, não o JSON reserializado —
qualquer diferença de espaço ou ordem muda o HMAC.
"""

from __future__ import annotations

import hashlib
import hmac

from . import config

CABECALHO = "HTTP_X_HUB_SIGNATURE_256"
PREFIXO = "sha256="


class AssinaturaInvalida(Exception):
    """O POST não veio (comprovadamente) da Meta."""


def conferir(corpo: bytes, cabecalho: str | None) -> None:
    """Levanta `AssinaturaInvalida` quando a assinatura não bate."""
    segredo = config.app_secret()
    if not segredo:
        raise AssinaturaInvalida(
            "WHATSAPP_APP_SECRET não configurado: o webhook recusa tudo até que "
            "ele exista. Sem o segredo não há como saber se o POST veio da Meta."
        )
    if not cabecalho or not cabecalho.startswith(PREFIXO):
        raise AssinaturaInvalida("Requisição sem cabeçalho X-Hub-Signature-256.")

    esperada = hmac.new(segredo.encode("utf-8"), corpo, hashlib.sha256).hexdigest()
    recebida = cabecalho[len(PREFIXO):]
    if not hmac.compare_digest(esperada, recebida):
        raise AssinaturaInvalida("Assinatura não confere com o corpo recebido.")


def assinar(corpo: bytes, segredo: str) -> str:
    """O cabeçalho que a Meta mandaria para este corpo. Existe para os testes."""
    return PREFIXO + hmac.new(segredo.encode("utf-8"), corpo, hashlib.sha256).hexdigest()
