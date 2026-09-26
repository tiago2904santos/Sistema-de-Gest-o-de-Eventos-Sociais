"""E-mails ao fornecedor enviados do sistema (m030: a OS)."""

import datetime as dt
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from . import documentos, services
from .models import AcaoHistoricoCoffeeBreak, ConfiguracaoCoffeeBreak
from .tests import BaseCoffeeBreakTestCase

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@override_settings(EMAIL_BACKEND=LOCMEM, DEFAULT_FROM_EMAIL="coffee@teste.local")
class EnviarOSTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        config = ConfiguracaoCoffeeBreak.atual()
        config.email_copia = "ascom@teste.local"
        config.save()
        self.solicitacao = self.criar_solicitacao(
            numero="21/2026", descricao_evento="Seminário regional", data_inicio_evento=dt.date(2026, 10, 5),
            horario_evento=dt.time(14, 0), local_entrega="Auditório da 1ª SDP",
            responsavel_recebimento="João 41 98888-0000",
        )
        self.url = reverse("coffee_break:enviar_os", args=[self.solicitacao.pk])
        self.client.force_login(self.ascom)

    def test_get_mostra_o_email_pronto_sem_enviar(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        valores = resposta.context["valores"]
        self.assertEqual(valores["para"], "contato@favoemel.com.br")
        self.assertEqual(valores["copia"], "ascom@teste.local")
        self.assertIn("21/2026", valores["assunto"])
        self.assertIn("Auditório da 1ª SDP", valores["texto"])
        self.assertIn("14:00", valores["texto"])
        self.assertContains(resposta, "Enviar e-mail")

    def test_post_envia_com_o_pdf_grava_a_data_e_o_historico(self):
        with mock.patch.object(documentos, "ordem_servico_pdf", return_value=b"%PDF-1.7 os"):
            resposta = self.client.post(self.url, {
                "para": "contato@favoemel.com.br, outro@favoemel.com.br",
                "copia": "ascom@teste.local",
                "assunto": "OS 21/2026",
                "texto": "Segue a OS.",
            })
        self.assertRedirects(resposta, reverse("coffee_break:editar", args=[self.solicitacao.pk]), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["contato@favoemel.com.br", "outro@favoemel.com.br"])
        self.assertEqual(email.cc, ["ascom@teste.local"])
        self.assertEqual(email.from_email, "coffee@teste.local")
        nome, conteudo, tipo = email.attachments[0]
        self.assertTrue(nome.startswith("Ordem de Servico 21-2026"))
        self.assertEqual(conteudo, b"%PDF-1.7 os")
        self.assertEqual(tipo, "application/pdf")
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.data_envio_ordem_servico, timezone.localdate())
        registro = self.solicitacao.historico.get(acao=AcaoHistoricoCoffeeBreak.EMAIL)
        self.assertIn("contato@favoemel.com.br", registro.descricao)
        self.assertIn("ascom@teste.local", registro.descricao)
        self.assertIn(nome, registro.descricao)
        self.assertEqual(registro.usuario, self.ascom)
        # A etapa 1 mostra a data do envio.
        self.assertContains(self.client.get(reverse("coffee_break:editar", args=[self.solicitacao.pk])), "OS enviada ao fornecedor em")

    def test_email_invalido_nao_envia(self):
        with mock.patch.object(documentos, "ordem_servico_pdf", return_value=b"%PDF"):
            resposta = self.client.post(self.url, {"para": "nao-e-email", "copia": "", "assunto": "x", "texto": ""})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "E-mail inválido")
        self.assertEqual(len(mail.outbox), 0)
        self.solicitacao.refresh_from_db()
        self.assertIsNone(self.solicitacao.data_envio_ordem_servico)

    def test_os_incompleta_nao_envia(self):
        self.solicitacao.local_entrega = ""
        self.solicitacao.save()
        resposta = self.client.post(self.url, {"para": "a@b.com", "assunto": "x", "texto": ""})
        self.assertContains(resposta, "Informe o local de entrega.")
        self.assertEqual(len(mail.outbox), 0)

    def test_painel_oferece_enviar_a_os_da_entrega_da_semana(self):
        hoje = dt.date(2026, 10, 1)
        grupos = {g["chave"]: g for g in services.fila_de_trabalho(hoje)}
        item = grupos["entrega"]["itens"][0]
        self.assertEqual(item["botao"], "Enviar a OS")
        self.assertEqual(item["url"], self.url)
