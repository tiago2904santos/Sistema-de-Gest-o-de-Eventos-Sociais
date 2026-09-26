"""Duplicar a solicitação e sugerir local e responsável já usados (m038)."""

import datetime as dt

from django.urls import reverse

from .models import HistoricoCoffeeBreak, SolicitacaoCoffeeBreak
from .tests import BaseCoffeeBreakTestCase


class DuplicarSolicitacaoTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.client.force_login(self.ascom)
        self.original = self.criar_solicitacao(
            municipio=self.curitiba, numero="07/2026", descricao_evento="Ciclo de Palestras - 1DP",
            quantidade=45, data_inicio_evento=dt.date(2026, 8, 10), horario_evento=dt.time(14, 0),
            local_entrega="1ª DP - Rua Teste, 100", responsavel_recebimento="Fulano 41 90000-0000",
            numero_nota_fiscal="123", numero_oficio="10/2026",
        )

    def test_duplicar_abre_a_nova_com_o_evento_e_sem_datas_nem_documentos(self):
        resposta = self.client.get(reverse("coffee_break:duplicar", args=[self.original.pk]))
        self.assertRedirects(resposta, reverse("coffee_break:nova") + f"?duplicar={self.original.pk}")
        resposta = self.client.get(resposta.url)
        valores = resposta.context["valores"]
        self.assertEqual(valores["municipio"], str(self.curitiba.pk))
        self.assertEqual(valores["descricao_evento"], "Ciclo de Palestras - 1DP")
        self.assertEqual(valores["quantidade"], "45")
        self.assertEqual(valores["local_entrega"], "1ª DP - Rua Teste, 100")
        self.assertEqual(valores["responsavel_recebimento"], "Fulano 41 90000-0000")
        self.assertEqual(valores["data_inicio_evento"], "")
        self.assertNotEqual(valores["numero"], "07/2026")
        self.assertContains(resposta, "Copiada de")
        self.assertContains(resposta, f'name="duplicar" value="{self.original.pk}"')

    def test_salvar_a_copia_registra_a_origem_no_historico(self):
        resposta = self.client.post(reverse("coffee_break:nova"), {
            "duplicar": self.original.pk, "municipio": self.curitiba.pk, "data_solicitacao": "2026-08-01",
            "descricao_evento": "Ciclo de Palestras - 1DP", "quantidade": "45",
            "data_inicio_evento": "2026-09-10", "local_entrega": "1ª DP - Rua Teste, 100",
            "responsavel_recebimento": "Fulano 41 90000-0000",
        })
        self.assertRedirects(resposta, reverse("coffee_break:solicitacoes"))
        copia = SolicitacaoCoffeeBreak.objects.exclude(pk=self.original.pk).get()
        self.assertEqual(copia.numero_nota_fiscal, "")
        self.assertEqual(copia.numero_oficio, "")
        historico = HistoricoCoffeeBreak.objects.filter(solicitacao=copia).first()
        self.assertIn("Duplicada da solicitação 07/2026", historico.descricao)

    def test_menu_da_linha_tem_duplicar(self):
        resposta = self.client.get(reverse("coffee_break:solicitacoes"))
        self.assertContains(resposta, reverse("coffee_break:duplicar", args=[self.original.pk]))

    def test_locais_ja_usados_no_municipio_sem_repetir(self):
        self.criar_solicitacao(
            municipio=self.curitiba, descricao_evento="Outro", data_inicio_evento=dt.date(2026, 9, 1),
            local_entrega="1ª DP - Rua Teste, 100", responsavel_recebimento="Fulano 41 90000-0000",
        )
        self.criar_solicitacao(
            municipio=self.curitiba, descricao_evento="Mais um", data_inicio_evento=dt.date(2026, 9, 5),
            local_entrega="Teatro Municipal", responsavel_recebimento="Beltrana",
        )
        self.criar_solicitacao(municipio=self.curitiba, descricao_evento="Sem local", local_entrega="")
        resposta = self.client.get(reverse("coffee_break:locais_entrega") + f"?municipio={self.curitiba.pk}")
        resultados = resposta.json()["resultados"]
        self.assertEqual([r["nome"] for r in resultados], ["Teatro Municipal", "1ª DP - Rua Teste, 100"])
        self.assertEqual(
            resultados[1]["campos"],
            {"local_entrega": "1ª DP - Rua Teste, 100", "responsavel_recebimento": "Fulano 41 90000-0000"},
        )
        self.assertEqual(self.client.get(reverse("coffee_break:locais_entrega")).json(), {"resultados": []})

    def test_tela_nova_traz_a_caixa_de_sugestao_sem_preencher(self):
        resposta = self.client.get(reverse("coffee_break:nova"))
        self.assertContains(resposta, "data-cb-locais")
        self.assertEqual(resposta.context["valores"]["local_entrega"], "")
