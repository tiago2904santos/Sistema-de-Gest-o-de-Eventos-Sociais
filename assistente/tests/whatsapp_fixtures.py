"""Dublês e payloads no formato real da Cloud API.

Os payloads são recortes do que a Meta entrega de verdade, incluindo o
`statuses` (recibo de entrega) que representa a maior parte do tráfego e não
pode ser confundido com mensagem de gente.
"""

import json

from django.test import override_settings

from assistente.models import VinculoWhatsApp
from assistente.whatsapp import assinatura

SEGREDO = "segredo-do-app-para-teste"
VERIFY = "token-de-verificacao-para-teste"

# Canal ligado e interpretação local: os testes não dependem de chave de API
# nem de rede, e o resultado não muda conforme o ambiente.
canal_configurado = override_settings(
    WHATSAPP_APP_SECRET=SEGREDO,
    WHATSAPP_VERIFY_TOKEN=VERIFY,
    WHATSAPP_TOKEN="token-de-acesso",
    WHATSAPP_PHONE_NUMBER_ID="123456",
    ASSISTENTE_LLM="deterministico",
)


class TransporteFake:
    """Registra o que sairia, em vez de falar com a Meta."""

    def __init__(self, audio=b"", mime="audio/ogg", falha=None):
        self.enviadas = []
        self._audio = audio
        self._mime = mime
        self._falha = falha

    def enviar(self, numero, texto):
        if self._falha:
            raise self._falha
        self.enviadas.append((numero, texto))
        return f"wamid.saida.{len(self.enviadas)}"

    def baixar_midia(self, media_id):
        return self._audio, self._mime


class TranscritorFake:
    def __init__(self, texto):
        self.texto = texto
        self.chamadas = 0

    def transcrever(self, audio, mime=""):
        self.chamadas += 1
        return self.texto


def vincular(usuario, numero="5541999998888"):
    return VinculoWhatsApp.objects.create(numero=numero, usuario=usuario)


def payload_texto(texto, *, numero="5541999998888", wa_id="wamid.001"):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "conta",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "123456"},
                            "contacts": [{"wa_id": numero, "profile": {"name": "Fulano"}}],
                            "messages": [
                                {
                                    "from": numero,
                                    "id": wa_id,
                                    "timestamp": "1790000000",
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def payload_audio(*, numero="5541999998888", wa_id="wamid.audio", media_id="midia.1"):
    corpo = payload_texto("", numero=numero, wa_id=wa_id)
    corpo["entry"][0]["changes"][0]["value"]["messages"] = [
        {
            "from": numero,
            "id": wa_id,
            "timestamp": "1790000000",
            "type": "audio",
            "audio": {"id": media_id, "mime_type": "audio/ogg; codecs=opus", "voice": True},
        }
    ]
    return corpo


def payload_recibo(numero="5541999998888"):
    """Recibo de entrega: mesmo formato, e não é mensagem de ninguém."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "conta",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "123456"},
                            "statuses": [
                                {
                                    "id": "wamid.saida.1",
                                    "status": "delivered",
                                    "recipient_id": numero,
                                    "timestamp": "1790000001",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def entregar(client, corpo, *, segredo=SEGREDO, url="/whatsapp/webhook/"):
    """Um POST assinado como a Meta assinaria."""
    cru = json.dumps(corpo).encode("utf-8")
    return client.post(
        url,
        data=cru,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=assinatura.assinar(cru, segredo),
    )
