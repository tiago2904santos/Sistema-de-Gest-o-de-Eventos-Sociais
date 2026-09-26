"""Virada de exercício: criar os lotes do novo ano com um clique (m040)."""

import datetime as dt
from decimal import Decimal

from django.urls import reverse

from .models import ContratoCoffeeBreak, LoteCoffeeBreak
from .tests import BaseCoffeeBreakTestCase


class ViradaDeExercicioTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.lote.orientacoes = "Entregar 30 min antes."
        self.lote.especificacoes_tecnicas = "Café, suco, salgados."
        self.lote.municipios_texto = "Curitiba e região"
        self.lote.save()
        self.vencido = ContratoCoffeeBreak.objects.create(
            fornecedor=self.fornecedor, numero="0100/2023", vigencia_fim=dt.date(2026, 6, 30),
        )
        self.lote_vencido = LoteCoffeeBreak.objects.create(
            contrato=self.vencido, numero=2, exercicio="2026", quantidade_total=50,
        )
        self.url = reverse("coffee_break:virada_exercicio")

    def _dados(self, **extra):
        dados = {
            "de": "2026",
            "form-TOTAL_FORMS": "2", "form-INITIAL_FORMS": "2",
            "form-0-lote": str(self.lote.pk), "form-0-criar": "on", "form-0-quantidade_total": "120",
            "form-0-empenho": "2027NE000123", "form-0-valor_empenho": "2400.00",
            "form-1-lote": str(self.lote_vencido.pk), "form-1-quantidade_total": "50",
        }
        dados.update(extra)
        return dados

    def test_so_administrador(self):
        self.client.force_login(self.ascom)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_tela_lista_os_lotes_e_trava_o_contrato_vencido(self):
        self.client.force_login(self.admin_modulo)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Abrir exercício 2027")
        linhas = {l["lote"].pk: l for l in resposta.context["linhas"]}
        self.assertEqual(linhas[self.lote.pk]["impedimento"], "")
        self.assertIn("Contrato vencido em 30/06/2026", linhas[self.lote_vencido.pk]["impedimento"])
        self.assertContains(self.client.get(reverse("coffee_break:lotes")), "Abrir exercício 2027")

    def test_cria_o_lote_do_ano_novo_copiando_municipios_e_textos(self):
        self.client.force_login(self.admin_modulo)
        resposta = self.client.post(self.url, self._dados())
        self.assertRedirects(resposta, reverse("coffee_break:lotes") + "?exercicio=2027", fetch_redirect_response=False)
        novo = LoteCoffeeBreak.objects.get(contrato=self.contrato, exercicio="2027")
        self.assertEqual(novo.numero, 1)
        self.assertEqual(novo.quantidade_total, 120)
        self.assertEqual(novo.empenho, "2027NE000123")
        self.assertEqual(novo.valor_empenho, Decimal("2400.00"))
        self.assertEqual(list(novo.municipios.all()), [self.curitiba])
        self.assertEqual(novo.orientacoes, "Entregar 30 min antes.")
        self.assertEqual(novo.especificacoes_tecnicas, "Café, suco, salgados.")
        self.assertEqual(novo.municipios_texto, "Curitiba e região")
        self.assertFalse(LoteCoffeeBreak.objects.filter(contrato=self.vencido, exercicio="2027").exists())
        self.lote.refresh_from_db()
        self.assertTrue(self.lote.ativo)
        # De novo: o lote de 2027 já existe, nada é duplicado.
        self.client.post(self.url, self._dados())
        self.assertEqual(LoteCoffeeBreak.objects.filter(contrato=self.contrato, exercicio="2027").count(), 1)

    def test_encerrar_os_anteriores(self):
        self.client.force_login(self.admin_modulo)
        self.client.post(self.url, self._dados(desativar="1"))
        self.lote.refresh_from_db()
        self.assertFalse(self.lote.ativo)
        self.lote_vencido.refresh_from_db()
        self.assertTrue(self.lote_vencido.ativo)

    def test_quantidade_obrigatoria_no_lote_marcado(self):
        self.client.force_login(self.admin_modulo)
        resposta = self.client.post(self.url, self._dados(**{"form-0-quantidade_total": ""}))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Informe a quantidade do novo exercício.")
        self.assertFalse(LoteCoffeeBreak.objects.filter(exercicio="2027").exists())
