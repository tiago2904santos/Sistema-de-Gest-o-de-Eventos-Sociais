"""O webhook: handshake, assinatura, idempotência — e a promessa de não
processar nada dentro do request."""

import json

from django.test import TestCase

from assistente.models import MensagemRecebida
from assistente.whatsapp import assinatura

from .fixtures import criar_usuario
from .whatsapp_fixtures import (
    SEGREDO,
    VERIFY,
    canal_configurado,
    entregar,
    payload_recibo,
    payload_texto,
    vincular,
)

URL = "/whatsapp/webhook/"


@canal_configurado
class Handshake(TestCase):
    def test_token_correto_devolve_o_desafio_em_texto_puro(self):
        resposta = self.client.get(
            URL,
            {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1234"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.content, b"1234")
        self.assertEqual(resposta["Content-Type"], "text/plain")

    def test_token_errado_e_recusado(self):
        resposta = self.client.get(
            URL,
            {"hub.mode": "subscribe", "hub.verify_token": "chutado", "hub.challenge": "1234"},
        )
        self.assertEqual(resposta.status_code, 403)

    def test_modo_diferente_de_subscribe_e_recusado(self):
        resposta = self.client.get(
            URL, {"hub.mode": "unsubscribe", "hub.verify_token": VERIFY, "hub.challenge": "1"}
        )
        self.assertEqual(resposta.status_code, 403)


@canal_configurado
class Entrega(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        vincular(self.usuario)

    def test_post_assinado_grava_a_mensagem(self):
        resposta = entregar(self.client, payload_texto("o que está pendente?"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(json.loads(resposta.content)["recebidas"], 1)
        gravada = MensagemRecebida.objects.get()
        self.assertEqual(gravada.texto, "o que está pendente?")
        self.assertEqual(gravada.numero, "5541999998888")

    def test_o_webhook_nao_processa_nada_dentro_do_request(self):
        """A Meta espera segundos; transcrever aqui estouraria o prazo."""
        entregar(self.client, payload_texto("o que está pendente?"))
        self.assertEqual(
            MensagemRecebida.objects.get().status, MensagemRecebida.Status.PENDENTE
        )

    def test_assinatura_invalida_e_recusada_e_nada_e_gravado(self):
        resposta = entregar(self.client, payload_texto("oi"), segredo="segredo-errado")
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(MensagemRecebida.objects.exists())

    def test_post_sem_assinatura_e_recusado(self):
        resposta = self.client.post(
            URL, data=json.dumps(payload_texto("oi")), content_type="application/json"
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(MensagemRecebida.objects.exists())

    def test_reentrega_da_mesma_mensagem_nao_duplica(self):
        """A Meta reentrega o que não confirmou; sem isto a mesma frase viraria
        duas viagens."""
        corpo = payload_texto("faça os documentos", wa_id="wamid.repetida")
        entregar(self.client, corpo)
        segunda = entregar(self.client, corpo)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(json.loads(segunda.content)["recebidas"], 0)
        self.assertEqual(MensagemRecebida.objects.count(), 1)

    def test_recibo_de_entrega_nao_vira_mensagem(self):
        resposta = entregar(self.client, payload_recibo())
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(MensagemRecebida.objects.exists())

    def test_corpo_ilegivel_com_assinatura_valida_nao_pede_reentrega(self):
        cru = b"isto nao e json"
        resposta = self.client.post(
            URL,
            data=cru,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=assinatura.assinar(cru, SEGREDO),
        )
        self.assertEqual(resposta.status_code, 200)

    def test_metodo_nao_suportado(self):
        self.assertEqual(self.client.delete(URL).status_code, 405)


class WebhookSemConfiguracao(TestCase):
    def test_sem_segredo_o_post_e_recusado(self):
        resposta = entregar(self.client, payload_texto("oi"))
        self.assertEqual(resposta.status_code, 403)

    def test_sem_verify_token_o_handshake_e_recusado(self):
        resposta = self.client.get(
            URL, {"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "1"}
        )
        self.assertEqual(resposta.status_code, 403)
