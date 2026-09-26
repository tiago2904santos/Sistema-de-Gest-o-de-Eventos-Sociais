"""Pedir coffee break direto do evento ou da palestra, já preenchido (m033)."""

import datetime as dt

from django.urls import reverse

from demandas_eventos.models import DemandaEvento, Tema
from solicitacoes.models import SolicitacaoEvento

from .models import SolicitacaoCoffeeBreak
from .tests import BaseCoffeeBreakTestCase


class PedirDoEventoTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.client.force_login(self.ascom)
        self.demanda = DemandaEvento.objects.create(
            municipio=self.curitiba, data_inicio_evento=dt.date(2026, 11, 10), hora_inicio=dt.time(9, 30),
            solicitante="Diretora Ana", telefone="41 99999-0000", data_solicitacao=dt.date(2026, 9, 1),
            quantidade_publico=80,
        )
        self.demanda.setores.add(self.setor_ascom)
        self.demanda.temas.add(Tema.objects.create(nome="Segurança na escola"))
        self.evento = SolicitacaoEvento.objects.create(
            municipio=self.curitiba, data_inicio_evento=dt.date(2026, 11, 20), local_evento="Ginásio Municipal",
            solicitante_nome="Carlos", contato="41 3333-0000", criado_por=self.ascom,
        )

    def test_nova_pela_palestra_vem_preenchida(self):
        resposta = self.client.get(reverse("coffee_break:nova") + f"?demanda={self.demanda.pk}")
        valores = resposta.context["valores"]
        self.assertEqual(valores["municipio"], str(self.curitiba.pk))
        self.assertEqual(valores["data_inicio_evento"], "2026-11-10")
        self.assertEqual(valores["horario_evento"], "09:30:00")
        self.assertEqual(valores["quantidade"], "80")
        self.assertIn("Segurança na escola", valores["descricao_evento"])
        self.assertIn("Diretora Ana 41 99999-0000", valores["responsavel_recebimento"])
        self.assertContains(resposta, "Preenchida a partir de")
        self.assertContains(resposta, f'name="demanda" value="{self.demanda.pk}"')

    def test_nova_pelo_evento_vem_preenchida_e_fica_ligada(self):
        resposta = self.client.get(reverse("coffee_break:nova") + f"?solicitacao={self.evento.pk}")
        valores = resposta.context["valores"]
        self.assertEqual(valores["local_entrega"], "Ginásio Municipal")
        self.assertEqual(valores["responsavel_recebimento"], "Carlos 41 3333-0000")
        resposta = self.client.post(reverse("coffee_break:nova"), {
            "solicitacao": self.evento.pk,
            "data_solicitacao": "2026-09-26",
            "municipio": self.curitiba.pk,
            "data_inicio_evento": "2026-11-20",
            "quantidade": "40",
            "descricao_evento": valores["descricao_evento"],
            "local_entrega": "Ginásio Municipal",
            "responsavel_recebimento": "Carlos 41 3333-0000",
        })
        self.assertEqual(resposta.status_code, 302, getattr(resposta, "context", {}) and resposta.context["form"].errors)
        cb = SolicitacaoCoffeeBreak.objects.get(solicitacao_evento=self.evento)
        self.assertEqual(cb.lote, self.lote)
        self.assertIn("Solicitação de evento", cb.historico.first().descricao)
        # O evento mostra a OS ligada e o botão.
        tela = self.client.get(reverse("solicitacoes:editar", args=[self.evento.pk]))
        self.assertContains(tela, f"OS {cb.numero}")
        self.assertContains(tela, "Pedir coffee break")
        # Remarcado o evento, a OS avisa.
        self.evento.data_inicio_evento = dt.date(2026, 11, 25)
        self.evento.save()
        tela = self.client.get(reverse("coffee_break:editar", args=[cb.pk]))
        self.assertContains(tela, "O evento foi remarcado para 25/11/2026")

    def test_origem_que_nao_enxerga_e_ignorada(self):
        outro = type(self.ascom).objects.create_user("outro", password="x")
        evento = SolicitacaoEvento.objects.create(municipio=self.curitiba, local_evento="Sigiloso", criado_por=outro)
        resposta = self.client.get(reverse("coffee_break:nova") + f"?solicitacao={evento.pk}")
        self.assertEqual(resposta.context["valores"]["local_entrega"], "")
        self.assertNotContains(resposta, "Preenchida a partir de")

    def test_palestra_mostra_o_botao_para_quem_tem_o_modulo(self):
        tela = self.client.get(reverse("demandas_eventos:editar", args=[self.demanda.pk]))
        self.assertContains(tela, f"?demanda={self.demanda.pk}")
