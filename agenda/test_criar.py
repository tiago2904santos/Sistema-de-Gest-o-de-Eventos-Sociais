"""'Criar aqui' (m135): do dia do calendário à tela nova, com as datas."""

from datetime import date

from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.urls import reverse

from core.periodo_url import datas_da_url, iniciais_do_periodo
from solicitacoes.tests import BaseSolicitacaoTestCase
from viagens_viagem.models import Viagem

from .criar import atalhos_de_criacao

User = get_user_model()


class DatasDaUrl(BaseSolicitacaoTestCase):
    def test_le_inicio_e_fim_e_corrige_fim_antes_do_inicio(self):
        self.assertEqual(datas_da_url(QueryDict("inicio=2026-10-05&fim=2026-10-07")), (date(2026, 10, 5), date(2026, 10, 7)))
        self.assertEqual(datas_da_url(QueryDict("inicio=2026-10-05")), (date(2026, 10, 5), date(2026, 10, 5)))
        self.assertEqual(datas_da_url(QueryDict("inicio=2026-10-05&fim=2026-10-01")), (date(2026, 10, 5), date(2026, 10, 5)))
        self.assertEqual(datas_da_url(QueryDict("inicio=ontem")), (None, None))
        self.assertEqual(iniciais_do_periodo(QueryDict("")), {})
        self.assertEqual(
            iniciais_do_periodo(QueryDict("inicio=2026-10-05&fim=2026-10-06")),
            {"data_inicio_evento": date(2026, 10, 5), "data_fim_evento": date(2026, 10, 6)},
        )


class AtalhosDoCalendario(BaseSolicitacaoTestCase):
    def test_so_os_modulos_que_a_pessoa_usa(self):
        self.assertEqual([a["slug"] for a in atalhos_de_criacao(self.solicitante)], ["solicitacao"])
        root = User.objects.create_superuser("criar_root", "criar_root@example.com", None)
        atalhos = {a["slug"]: a for a in atalhos_de_criacao(root)}
        self.assertEqual(set(atalhos), {"viagem", "solicitacao", "coffee", "demanda"})
        self.assertEqual(atalhos["viagem"]["metodo"], "post")
        self.assertEqual(atalhos["viagem"]["url"], reverse("viagens_viagem:criar"))
        self.assertEqual(atalhos["demanda"]["url"], reverse("demandas_eventos:nova"))

    def test_painel_traz_o_menu_com_as_telas(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("agenda:painel"))
        self.assertContains(resposta, 'id="ag-criar"')
        self.assertContains(resposta, 'data-base="' + reverse("solicitacoes:nova") + '"')
        self.assertNotContains(resposta, reverse("viagens_viagem:criar"))


class TelasNovasLeemAsDatas(BaseSolicitacaoTestCase):
    def test_nova_solicitacao_abre_com_o_periodo(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:nova"), {"inicio": "2026-10-05", "fim": "2026-10-07"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'value="2026-10-05"')
        self.assertContains(resposta, 'value="2026-10-07"')
        # Sem período (ou com lixo) a tela abre em branco, como sempre.
        resposta = self.client.get(reverse("solicitacoes:nova"), {"inicio": "lixo"})
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'value="2026-10-05"')

    def test_nova_palestra_e_novo_coffee_abrem_com_o_periodo(self):
        root = User.objects.create_superuser("criar_root2", "criar_root2@example.com", None)
        self.client.force_login(root)
        resposta = self.client.get(reverse("demandas_eventos:nova"), {"inicio": "2026-10-05", "fim": "2026-10-06"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'value="2026-10-05"')
        self.assertContains(resposta, 'value="2026-10-06"')
        # O coffee break é de um dia só: entra a data inicial, o fim é ignorado.
        resposta = self.client.get(reverse("coffee_break:nova"), {"inicio": "2026-10-05", "fim": "2026-10-06"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'value="2026-10-05"')
        self.assertNotContains(resposta, 'value="2026-10-06"')

    def test_nova_viagem_por_post_nasce_com_o_periodo(self):
        root = User.objects.create_superuser("criar_root3", "criar_root3@example.com", None)
        self.client.force_login(root)
        resposta = self.client.post(reverse("viagens_viagem:criar"), {"inicio": "2026-10-05", "fim": "2026-10-07"})
        self.assertEqual(resposta.status_code, 302)
        viagem = Viagem.objects.latest("pk")
        self.assertEqual((viagem.data_inicio, viagem.data_fim), (date(2026, 10, 5), date(2026, 10, 7)))
        self.assertIn(reverse("viagens_viagem:etapa", args=[viagem.pk, 1]), resposta["Location"])
        # Sem datas, o rascunho continua nascendo vazio.
        self.client.post(reverse("viagens_viagem:criar"))
        self.assertIsNone(Viagem.objects.latest("pk").data_inicio)
