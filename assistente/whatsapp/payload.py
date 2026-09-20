"""Tradução do JSON da Cloud API para o que o sistema entende.

Defensivo de propósito: o corpo é **dado externo**, e um formato inesperado
não pode derrubar o webhook — a Meta reentrega o que não recebeu 200, e um
erro aqui viraria um laço de reentrega infinito sobre uma mensagem que nunca
vai ser processada.

O que não é mensagem de gente é descartado em silêncio. O caso mais comum é o
recibo de entrega (`statuses`): ele chega no mesmo formato, é a maioria do
tráfego, e tratá-lo como mensagem faria o assistente responder aos próprios
recibos.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import MensagemRecebida
from .numeros import normalizar


@dataclass(frozen=True)
class Entrada:
    wa_message_id: str
    numero: str
    tipo: str
    texto: str = ""
    media_id: str = ""


def _lista(valor):
    return valor if isinstance(valor, list) else []


def _dicionario(valor):
    return valor if isinstance(valor, dict) else {}


def extrair(corpo) -> list[Entrada]:
    """As mensagens de gente dentro de um payload de webhook."""
    entradas: list[Entrada] = []
    for entry in _lista(_dicionario(corpo).get("entry")):
        for change in _lista(_dicionario(entry).get("changes")):
            valor = _dicionario(_dicionario(change).get("value"))
            for bruta in _lista(valor.get("messages")):
                entrada = _uma(_dicionario(bruta))
                if entrada:
                    entradas.append(entrada)
    return entradas


def _uma(bruta: dict) -> Entrada | None:
    wa_id = str(bruta.get("id") or "").strip()
    numero = normalizar(bruta.get("from"))
    if not wa_id or not numero:
        return None

    tipo_bruto = str(bruta.get("type") or "").strip().lower()
    if tipo_bruto == "text":
        texto = str(_dicionario(bruta.get("text")).get("body") or "").strip()
        return Entrada(wa_id, numero, MensagemRecebida.Tipo.TEXTO, texto=texto)
    if tipo_bruto in {"audio", "voice"}:
        media_id = str(_dicionario(bruta.get("audio")).get("id") or "").strip()
        return Entrada(wa_id, numero, MensagemRecebida.Tipo.AUDIO, media_id=media_id)

    # Imagem, documento, figurinha, localização: reconhecidos para poderem ser
    # respondidos com uma frase útil, em vez de sumirem sem explicação.
    return Entrada(wa_id, numero, MensagemRecebida.Tipo.OUTRO, texto=tipo_bruto)
