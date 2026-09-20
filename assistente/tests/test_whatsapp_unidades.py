"""As três peças que precisam estar certas antes de qualquer fluxo: número,
assinatura e leitura do payload."""

import json

from django.test import SimpleTestCase, TestCase, override_settings

from assistente.whatsapp import assinatura, numeros, payload

from .fixtures import criar_usuario
from .whatsapp_fixtures import (
    SEGREDO,
    payload_audio,
    payload_recibo,
    payload_texto,
    vincular,
)


class NonoDigito(TestCase):
    """O erro que faria o assistente "não responder pra fulano" em produção."""

    def test_numero_guardado_com_nove_casa_com_a_entrega_sem_nove(self):
        usuario = criar_usuario()
        vincular(usuario, "5541999998888")
        achado = numeros.buscar_vinculo("554199998888")  # como a Meta pode entregar
        self.assertIsNotNone(achado)
        self.assertEqual(achado.usuario, usuario)

    def test_numero_guardado_sem_nove_casa_com_a_entrega_com_nove(self):
        usuario = criar_usuario()
        vincular(usuario, "554199998888")
        self.assertIsNotNone(numeros.buscar_vinculo("5541999998888"))

    def test_numero_de_outro_pais_e_comparado_como_veio(self):
        usuario = criar_usuario()
        vincular(usuario, "351912345678")
        self.assertIsNotNone(numeros.buscar_vinculo("+351 912 345 678"))
        self.assertIsNone(numeros.buscar_vinculo("351912345679"))

    def test_vinculo_inativo_nao_conta(self):
        usuario = criar_usuario()
        vinculo = vincular(usuario)
        vinculo.ativo = False
        vinculo.save()
        self.assertIsNone(numeros.buscar_vinculo(vinculo.numero))

    def test_numero_sem_digito_nao_busca_nada(self):
        self.assertEqual(numeros.variantes("sem números aqui"), [])


@override_settings(WHATSAPP_APP_SECRET=SEGREDO)
class Assinatura(SimpleTestCase):
    corpo = b'{"entry":[]}'

    def test_assinatura_correta_passa(self):
        assinatura.conferir(self.corpo, assinatura.assinar(self.corpo, SEGREDO))

    def test_assinatura_de_outro_segredo_e_recusada(self):
        with self.assertRaises(assinatura.AssinaturaInvalida):
            assinatura.conferir(self.corpo, assinatura.assinar(self.corpo, "outro"))

    def test_corpo_alterado_e_recusado(self):
        cabecalho = assinatura.assinar(self.corpo, SEGREDO)
        with self.assertRaises(assinatura.AssinaturaInvalida):
            assinatura.conferir(b'{"entry":[1]}', cabecalho)

    def test_sem_cabecalho_e_recusado(self):
        with self.assertRaises(assinatura.AssinaturaInvalida):
            assinatura.conferir(self.corpo, None)


class AssinaturaSemSegredo(SimpleTestCase):
    @override_settings(WHATSAPP_APP_SECRET="")
    def test_sem_segredo_configurado_recusa_tudo(self):
        """Falha fechado: um webhook aberto é pior que um webhook desligado."""
        corpo = b'{"entry":[]}'
        with self.assertRaises(assinatura.AssinaturaInvalida):
            assinatura.conferir(corpo, assinatura.assinar(corpo, "qualquer"))


class LeituraDoPayload(SimpleTestCase):
    def test_texto(self):
        (entrada,) = payload.extrair(payload_texto("o que está pendente?"))
        self.assertEqual(entrada.tipo, "TEXTO")
        self.assertEqual(entrada.texto, "o que está pendente?")
        self.assertEqual(entrada.numero, "5541999998888")

    def test_audio_traz_a_midia_e_nao_texto(self):
        (entrada,) = payload.extrair(payload_audio())
        self.assertEqual(entrada.tipo, "AUDIO")
        self.assertEqual(entrada.media_id, "midia.1")
        self.assertEqual(entrada.texto, "")

    def test_recibo_de_entrega_nao_e_mensagem(self):
        """Sem isto o assistente responderia aos próprios recibos."""
        self.assertEqual(payload.extrair(payload_recibo()), [])

    def test_payload_estranho_nao_derruba_nada(self):
        for corpo in ({}, {"entry": "nada"}, {"entry": [{"changes": None}]}, []):
            self.assertEqual(payload.extrair(corpo), [])

    def test_tipo_nao_suportado_e_reconhecido_em_vez_de_sumir(self):
        corpo = payload_texto("x")
        corpo["entry"][0]["changes"][0]["value"]["messages"][0] = {
            "from": "5541999998888", "id": "wamid.img", "type": "image",
            "image": {"id": "i.1"},
        }
        (entrada,) = payload.extrair(corpo)
        self.assertEqual(entrada.tipo, "OUTRO")
