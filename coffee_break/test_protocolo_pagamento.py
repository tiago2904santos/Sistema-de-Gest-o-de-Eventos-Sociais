"""m034: pacote do protocolo de pagamento para abrir à mão no eProtocolo."""

from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import HistoricoCoffeeBreak
from . import protocolo_pagamento
from .tests import EtapasBase


class ProtocoloPagamentoTests(EtapasBase):
    def test_validar_numero(self):
        self.assertEqual(protocolo_pagamento.validar_numero("26.617.058-0"), "26.617.058-0")
        self.assertEqual(protocolo_pagamento.validar_numero(" 266170580 "), "26.617.058-0")
        for invalido in ("", "2026.050880.000", "26.617.058", "ab.cde.fgh-i", "1234567890"):
            with self.subTest(invalido=invalido), self.assertRaises(ValidationError):
                protocolo_pagamento.validar_numero(invalido)

    def test_tela_mostra_passo_a_passo_copiar_e_baixar(self):
        self._completar_para_protocolo(self.solicitacao)
        resposta = self.client.get(reverse("coffee_break:etapa_protocolo", args=[self.solicitacao.pk]))
        self.assertContains(resposta, "Como abrir o protocolo de pagamento")
        self.assertContains(resposta, "data-copiar=")
        self.assertContains(resposta, "data-baixar-documentos")
        self.assertContains(resposta, reverse("coffee_break:baixar_arquivos", args=[self.solicitacao.pk]))
        self.assertContains(resposta, 'id="form-registrar-protocolo"')

    def test_registrar_protocolo_com_nota_vira_o_de_pagamento(self):
        self._completar_para_protocolo(self.solicitacao)
        url = reverse("coffee_break:registrar_protocolo", args=[self.solicitacao.pk])
        resposta = self.client.post(url, {"numero_protocolo": "266170580"})
        self.assertRedirects(
            resposta, reverse("coffee_break:etapa_protocolo", args=[self.solicitacao.pk]) + "#sec-pagamento",
            fetch_redirect_response=False,
        )
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.protocolo_pcpr_oficio, "26.617.058-0")
        self.assertEqual(self.solicitacao.protocolo_pagamento, "26.617.058-0")
        self.assertTrue(
            HistoricoCoffeeBreak.objects.filter(
                solicitacao=self.solicitacao, descricao__icontains="Protocolo aberto no eProtocolo registrado: 26.617.058-0"
            ).exists()
        )

    def test_formato_invalido_nao_grava(self):
        url = reverse("coffee_break:registrar_protocolo", args=[self.solicitacao.pk])
        resposta = self.client.post(url, {"numero_protocolo": "2026.050880.000"}, follow=True)
        self.assertContains(resposta, "00.000.000-0")
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.protocolo_pcpr_oficio, "")

    def test_sem_nota_fica_so_no_oficio(self):
        url = reverse("coffee_break:registrar_protocolo", args=[self.solicitacao.pk])
        resposta = self.client.post(url, {"numero_protocolo": "26.617.058-0"}, follow=True)
        self.assertContains(resposta, "quando a nota fiscal for registrada")
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.protocolo_pcpr_oficio, "26.617.058-0")
        self.assertEqual(self.solicitacao.protocolo_pagamento, "")

    def test_bloqueada_e_so_post_e_so_modulo(self):
        url = reverse("coffee_break:registrar_protocolo", args=[self.solicitacao.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.solicitacao.cancelada = True
        self.solicitacao.save()
        self.client.post(url, {"numero_protocolo": "26.617.058-0"})
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.protocolo_pcpr_oficio, "")
        self.client.logout()
        self.assertEqual(self.client.post(url, {"numero_protocolo": "26.617.058-0"}).status_code, 302)
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.client.post(url, {"numero_protocolo": "26.617.058-0"}).status_code, 403)

    def test_payload_da_integracao_futura_sem_rede(self):
        self._completar_para_protocolo(self.solicitacao)
        payload = protocolo_pagamento.payload_integracao(self.solicitacao)
        self.assertEqual(payload["numeroDocumento"], "124/2026")
        self.assertIn("8957", payload["descricao"])
        self.assertEqual(payload["interessado"]["cnpj"], self.fornecedor.cnpj)
        self.assertEqual([d["ordem"] for d in payload["documentos"]], list(range(1, len(payload["documentos"]) + 1)))
