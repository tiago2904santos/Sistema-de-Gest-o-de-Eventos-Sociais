"""Pauta da semana (m136): o PDF e o e-mail de segunda-feira."""

from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from accounts.models import PautaSemanal
from solicitacoes.tests import BaseSolicitacaoTestCase

from . import pauta

User = get_user_model()


class MontagemDaPauta(BaseSolicitacaoTestCase):
    def setUp(self):
        super().setUp()
        # Segunda 28/09 a domingo 04/10 de 2026.
        self.dois_dias = self.criar_solicitacao(criado_por=self.solicitante, data_inicio_evento=date(2026, 9, 29), data_fim_evento=date(2026, 9, 30))
        self.cancelada = self.criar_solicitacao(criado_por=self.solicitante, data_inicio_evento=date(2026, 10, 1), data_fim_evento=date(2026, 10, 1))
        from solicitacoes.models import DecisaoDG, StatusSolicitacao

        self.cancelada.status = StatusSolicitacao.CANCELADA
        self.cancelada.decisao_dg = DecisaoDG.CANCELADO
        self.cancelada.save()

    def test_um_bloco_por_dia_e_compromisso_de_dois_dias_continua(self):
        contexto = pauta.montar(self.solicitante, date(2026, 9, 28), date(2026, 10, 4), hoje=date(2026, 9, 28))
        self.assertEqual(contexto["titulo"], "Pauta da semana")
        self.assertEqual(len(contexto["dias"]), 7)
        terca, quarta, quinta = contexto["dias"][1], contexto["dias"][2], contexto["dias"][3]
        self.assertEqual(len(terca["itens"]), 1)
        self.assertFalse(terca["itens"][0]["continua"])
        self.assertEqual(terca["itens"][0]["ate"], date(2026, 9, 30))
        self.assertTrue(quarta["itens"][0]["continua"])
        # Cancelada fica de fora da pauta.
        self.assertEqual(quinta["itens"], [])
        self.assertEqual(contexto["total"], 2)
        self.assertEqual(terca["itens"][0]["local"], "Praça central")

    def test_html_da_pauta(self):
        contexto = pauta.montar(self.solicitante, date(2026, 9, 28), date(2026, 10, 4))
        html = pauta.html(contexto)
        self.assertIn("Pauta da semana", html)
        self.assertIn("Cidade Teste", html)
        self.assertIn("segunda-feira", html)

    def test_baixar_exige_login_e_devolve_pdf_ou_html(self):
        url = reverse("agenda:pauta")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.solicitante)
        resposta = self.client.get(url, {"inicio": "2026-09-28", "fim": "2026-10-04", "formato": "html"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Cidade Teste")
        with mock.patch("agenda.pauta.pdf", return_value=b"%PDF-1.4 teste"):
            resposta = self.client.get(url, {"inicio": "2026-09-28", "fim": "2026-10-04"})
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertIn("pauta_2026-09-28_2026-10-04.pdf", resposta["Content-Disposition"])
        # Sem WeasyPrint: cai no HTML, com o aviso, em vez de erro 500.
        with mock.patch("agenda.pauta.pdf", return_value=None):
            resposta = self.client.get(url, {"inicio": "2026-09-28", "fim": "2026-10-04"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Salvar como PDF")

    def test_periodo_invalido_cai_na_semana_atual_e_grande_demais_e_cortado(self):
        self.client.force_login(self.solicitante)
        with mock.patch("agenda.pauta.montar", wraps=pauta.montar) as montar:
            self.client.get(reverse("agenda:pauta"), {"inicio": "x", "formato": "html"})
            inicio, fim = montar.call_args.args[1:3]
            self.assertEqual(inicio.weekday(), 0)
            self.assertEqual((fim - inicio).days, 6)
            self.client.get(reverse("agenda:pauta"), {"inicio": "2026-01-01", "fim": "2027-01-01", "formato": "html"})
            inicio, fim = montar.call_args.args[1:3]
            self.assertEqual((fim - inicio).days, pauta.MAX_DIAS - 1)

    def test_painel_tem_o_botao_e_a_opcao_do_email(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("agenda:painel"))
        self.assertContains(resposta, 'id="ag-pauta"')
        self.assertContains(resposta, reverse("agenda:pauta"))
        self.assertContains(resposta, "pauta_ligar")
        self.client.post(reverse("agenda:assinatura"), {"acao": "pauta_ligar"})
        self.assertTrue(PautaSemanal.objects.get(usuario=self.solicitante).ativa)
        self.assertContains(self.client.get(reverse("agenda:painel")), "pauta_desligar")
        self.client.post(reverse("agenda:assinatura"), {"acao": "pauta_desligar"})
        self.assertFalse(PautaSemanal.objects.get(usuario=self.solicitante).ativa)


class EnvioSemanal(BaseSolicitacaoTestCase):
    def setUp(self):
        super().setUp()
        User.objects.filter(pk=self.solicitante.pk).update(email="sol@example.com")
        self.solicitante.refresh_from_db()
        PautaSemanal.objects.create(usuario=self.solicitante, ativa=True)
        PautaSemanal.objects.create(usuario=self.gestor, ativa=True)  # sem e-mail: não recebe
        PautaSemanal.objects.create(usuario=self.administrador, ativa=False)
        self.criar_solicitacao(criado_por=self.solicitante, data_inicio_evento=date(2026, 9, 30), data_fim_evento=date(2026, 9, 30))

    def test_manda_uma_vez_por_semana_com_o_pdf_anexo(self):
        with mock.patch("agenda.pauta.pdf", return_value=b"%PDF-1.4 teste"):
            self.assertEqual(pauta.enviar_pauta_semanal(date(2026, 9, 28)), 1)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["sol@example.com"])
        self.assertIn("Pauta da semana", email.subject)
        self.assertIn("28/09 a 04/10", email.subject)
        self.assertIn("Cidade Teste", email.body)
        self.assertEqual(email.attachments[0][0], "pauta_2026-09-28_2026-10-04.pdf")
        self.assertEqual(PautaSemanal.objects.get(usuario=self.solicitante).enviada_para_semana, date(2026, 9, 28))
        # Terça da mesma semana: já foi. Segunda seguinte: vai de novo.
        with mock.patch("agenda.pauta.pdf", return_value=None):
            self.assertEqual(pauta.enviar_pauta_semanal(date(2026, 9, 29)), 0)
            self.assertEqual(pauta.enviar_pauta_semanal(date(2026, 10, 5)), 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].attachments, [])

    def test_se_a_segunda_passou_em_branco_sai_no_primeiro_dia_util_seguinte(self):
        with mock.patch("agenda.pauta.pdf", return_value=None):
            self.assertEqual(pauta.enviar_pauta_semanal(date(2026, 10, 3)), 0)  # sábado
            self.assertEqual(pauta.enviar_pauta_semanal(date(2026, 9, 30)), 1)  # quarta

    def test_a_rotina_diaria_chama_o_envio(self):
        from core import rotinas

        with mock.patch("agenda.pauta.enviar_pauta_semanal", return_value=0) as enviar, \
                mock.patch("solicitacoes.lembretes.enviar_lembretes", return_value=0), \
                mock.patch("viagens_prestacoes.avisos.avisar_prazos", return_value=0), \
                mock.patch("viagens_prestacoes.avisos.avisar_viagens", return_value=0), \
                mock.patch("core.rotinas.resumo_do_dia", return_value=0):
            rotinas.rodar(date(2026, 9, 28))
        enviar.assert_called_once_with(date(2026, 9, 28))
