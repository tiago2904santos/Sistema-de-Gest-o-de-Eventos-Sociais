from datetime import date, time
from urllib.parse import unquote

from django.urls import reverse

from . import services
from .models import AcaoHistoricoDemanda, Palestrante, RespostaPadrao, StatusDemanda
from .tests import BaseDemandasTestCase

MODAL = {"HTTP_X_CADASTRO_MODAL": "1"}


class PreencherRespostaTests(BaseDemandasTestCase):
    def test_marcadores_viram_os_dados_da_palestra(self):
        demanda = self.criar_demanda(
            solicitante="Colégio Exemplo",
            data_inicio_evento=date(2026, 10, 5),
            hora_inicio=time(14, 30),
            municipio_texto="Cidade Fictícia",
        )
        demanda.palestrantes.add(Palestrante.objects.create(nome="Servidora Exemplo"))
        resposta = RespostaPadrao(
            tipo="Confirmação",
            mensagem="Olá, {solicitante}! Dia {data} às {horario}, em {municipio}, "
            "com {palestrante}, tema {tema}. {desconhecido}Chave solta: { e }.",
        )
        self.assertEqual(
            services.preencher_resposta(resposta, demanda),
            "Olá, Colégio Exemplo! Dia 05/10/2026 às 14:30, em Cidade Fictícia, "
            "com Servidora Exemplo, tema Crimes virtuais. Chave solta: { e }.",
        )

    def test_links_de_email_e_whatsapp(self):
        demanda = self.criar_demanda(
            email="contato@example.org", telefone="(41) 99999-0000", assunto_email="Pedido de palestra"
        )
        email = services.link_email(demanda, "Olá & até")
        self.assertTrue(email.startswith("mailto:contato@example.org?subject="))
        self.assertIn("Pedido de palestra", unquote(email))
        self.assertIn("body=Ol%C3%A1%20%26%20at%C3%A9", email)
        self.assertTrue(services.link_whatsapp(demanda, "Oi").startswith("https://wa.me/5541999990000?text=Oi"))
        sem_contato = self.criar_demanda()
        self.assertEqual(services.link_email(sem_contato, "x"), "")
        self.assertEqual(services.link_whatsapp(sem_contato, "x"), "")


class ResponderViewTests(BaseDemandasTestCase):
    def setUp(self):
        self.resposta = RespostaPadrao.objects.create(
            tipo="Aguardando data", mensagem="Prezado(a) {solicitante}, aguardamos a data."
        )
        self.demanda = self.criar_demanda(solicitante="Escola Exemplo", email="escola@example.org")
        self.url = reverse("demandas_eventos:responder", args=[self.demanda.pk])

    def test_modal_mostra_a_resposta_preenchida_e_os_atalhos(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url, **MODAL)
        self.assertTemplateUsed(resposta, "pages/demandas_eventos/_modal_responder.html")
        self.assertContains(resposta, "Prezado(a) Escola Exemplo, aguardamos a data.")
        self.assertContains(resposta, "mailto:escola@example.org")
        # Sem telefone, não há atalho de WhatsApp.
        self.assertNotContains(resposta, "wa.me")

    def test_registrar_resposta_grava_historico_e_muda_status(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(
            self.url, {"resposta": self.resposta.pk, "novo_status": StatusDemanda.AGUARDANDO_RETORNO}, **MODAL
        )
        self.assertEqual(resposta.json(), {"ok": True})
        self.demanda.refresh_from_db()
        self.assertEqual(self.demanda.status, StatusDemanda.AGUARDANDO_RETORNO)
        registro = self.demanda.historico.get(acao=AcaoHistoricoDemanda.RESPOSTA)
        self.assertIn("Prezado(a) Escola Exemplo", registro.descricao)
        self.assertIn("Aguardando data", registro.descricao)

    def test_sem_mudar_status_e_sem_escolha(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url, {"resposta": ""}, **MODAL)
        self.assertContains(resposta, "Escolha a resposta enviada.")
        resposta = self.client.post(self.url, {"resposta": self.resposta.pk})
        self.assertRedirects(resposta, reverse("demandas_eventos:editar", args=[self.demanda.pk]), fetch_redirect_response=False)
        self.demanda.refresh_from_db()
        self.assertEqual(self.demanda.status, StatusDemanda.PENDENTE)
        self.assertTrue(self.demanda.historico.filter(acao=AcaoHistoricoDemanda.RESPOSTA).exists())

    def test_status_fora_da_lista_e_recusado(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(
            self.url, {"resposta": self.resposta.pk, "novo_status": StatusDemanda.ATENDIDA}, **MODAL
        )
        self.assertContains(resposta, "Escolha um status válido.")
        self.assertFalse(self.demanda.historico.filter(acao=AcaoHistoricoDemanda.RESPOSTA).exists())

    def test_tela_propria_lista_e_formulario_levam_ao_responder(self):
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(self.url), "Registrar resposta enviada")
        self.assertContains(self.client.get(reverse("demandas_eventos:lista")), f'href="{self.url}" data-cadastro-modal')
        resposta = self.client.get(reverse("demandas_eventos:editar", args=[self.demanda.pk]))
        self.assertContains(resposta, f'href="{self.url}" data-cadastro-modal')
        self.assertContains(resposta, "data-cadastro-dialog")

    def test_outro_setor_nao_responde(self):
        self.client.force_login(self.outro)
        self.assertEqual(self.client.get(self.url).status_code, 404)
