"""Registrar a entrega e as ocorrências com o fornecedor (m042)."""

import datetime as dt
import json

from django.urls import reverse
from django.utils import timezone

from . import services
from .models import OcorrenciaEntrega, TipoOcorrencia
from .tests import BaseCoffeeBreakTestCase


class EntregaTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.client.force_login(self.ascom)
        self.solicitacao = self.criar_solicitacao(numero="51/2026", data_inicio_evento=timezone.localdate() - dt.timedelta(days=1))
        self.url = reverse("coffee_break:entrega", args=[self.solicitacao.pk])

    def test_registra_a_entrega_pelo_modal(self):
        resposta = self.client.post(
            self.url, {"tipo": "ENTREGUE", "avaliacao": "5", "recebido_por": "Ana"}, HTTP_X_CADASTRO_MODAL="1"
        )
        self.assertEqual(json.loads(resposta.content), {"ok": True})
        ocorrencia = OcorrenciaEntrega.objects.get()
        self.assertEqual(ocorrencia.registrada_por, self.ascom)
        self.assertEqual(ocorrencia.avaliacao, 5)
        self.assertTrue(self.solicitacao.historico.filter(descricao__contains="Entrega registrada").exists())
        self.assertContains(self.client.get(reverse("coffee_break:editar", args=[self.solicitacao.pk])), "Entregue sem ocorrência")

    def test_ocorrencia_exige_descricao_e_nota_de_1_a_5(self):
        resposta = self.client.post(self.url, {"tipo": "ATRASO", "avaliacao": "7"})
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("descricao", resposta.context["form"].errors)
        self.assertIn("avaliacao", resposta.context["form"].errors)
        self.assertFalse(OcorrenciaEntrega.objects.exists())

    def test_so_a_partir_do_dia_do_evento(self):
        futura = self.criar_solicitacao(numero="52/2026", data_inicio_evento=timezone.localdate() + dt.timedelta(days=3))
        self.client.post(reverse("coffee_break:entrega", args=[futura.pk]), {"tipo": "ENTREGUE"})
        self.assertFalse(OcorrenciaEntrega.objects.exists())

    def test_resumo_do_fornecedor_no_cadastro(self):
        OcorrenciaEntrega.objects.create(solicitacao=self.solicitacao, tipo=TipoOcorrencia.ENTREGUE, avaliacao=5)
        outra = self.criar_solicitacao(numero="53/2026", data_inicio_evento=dt.date(2026, 8, 1))
        OcorrenciaEntrega.objects.create(solicitacao=outra, tipo=TipoOcorrencia.ATRASO, avaliacao=3, descricao="40 min")
        resumo = services.resumo_do_fornecedor(self.fornecedor)
        self.assertEqual(resumo["os"], 2)
        self.assertEqual(resumo["media"], 4.0)
        self.assertEqual(resumo["por_tipo"], [("Atraso na entrega", 1)])
        self.assertEqual(services.texto_do_resumo(resumo), "2 entregas registradas · nota média 4,0 · 1 ocorrência")
        self.client.force_login(self.admin_modulo)
        tela = self.client.get(reverse("coffee_break:cadastro_lista", args=["fornecedores"]))
        self.assertContains(tela, "2 entregas registradas")
