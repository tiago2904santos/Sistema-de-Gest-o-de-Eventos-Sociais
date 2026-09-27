"""Visão anual e link com os filtros (m137)."""

from django.urls import reverse

from solicitacoes.tests import BaseSolicitacaoTestCase

from .tests import _eventos


class VisaoAnual(BaseSolicitacaoTestCase):
    def test_painel_tem_a_visao_ano_e_o_copiar_link(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("agenda:painel"))
        self.assertContains(resposta, 'data-view="multiMonthYear"')
        self.assertContains(resposta, "data-ag-copiar-link")

    def test_servidor_aceita_o_periodo_da_visao_anual(self):
        """O multiMonthYear pede o ano com as semanas de borda: cabe no teto."""
        self.client.force_login(self.solicitante)
        self.assertEqual(_eventos(self.client, "2025-12-28", "2027-01-10").status_code, 200)

    def test_a_url_com_filtros_abre_o_painel_normalmente(self):
        """Os filtros vivem na query string e são lidos pelo JS; o servidor só ignora."""
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("agenda:painel"), {"view": "multiMonthYear", "data": "2026-10-01", "municipio": "Londrina", "fontes": "viagem"})
        self.assertEqual(resposta.status_code, 200)
