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


class LeituraDaOBTests(BaseCoffeeBreakTestCase):
    def test_le_numero_data_e_valor(self):
        from decimal import Decimal

        from .ordem_bancaria import dados_no_texto

        texto = "ORDEM BANCÁRIA\nNúmero: 2026OB004512\nData de emissão: 14/10/2026\nValor líquido R$ 1.264,20"
        dados = dados_no_texto(texto)
        self.assertEqual(dados["numero"], "2026OB004512")
        self.assertEqual(dados["data"], dt.date(2026, 10, 14))
        self.assertEqual(dados["valor"], Decimal("1264.20"))
        self.assertEqual(dados_no_texto("sem nada"), {"numero": "", "data": None, "valor": None})


@override_settings(EMAIL_BACKEND=LOCMEM)
class OrdemBancariaTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        import tempfile
        from decimal import Decimal

        pasta = tempfile.TemporaryDirectory(prefix="coffee-ob-")
        self.addCleanup(pasta.cleanup)
        ajuste = override_settings(MEDIA_ROOT=pasta.name)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        self.client.force_login(self.ascom)
        comum = {
            "numero_nota_fiscal": "8957", "protocolo_pagamento": "26.617.058-0",
            "data_atesto_gaf": dt.date(2026, 9, 20), "valor_unitario": Decimal("20.00"),
        }
        self.principal = self.criar_solicitacao(numero="31/2026", quantidade=30, valor_nota_fiscal=Decimal("600.00"), **comum)
        comum["numero_nota_fiscal"] = "8958"
        self.outra = self.criar_solicitacao(
            numero="32/2026", quantidade=10, valor_nota_fiscal=Decimal("200.00"), pagamento_com=self.principal, **comum
        )

    def _anexar(self, lidos):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .tests import _pdf_em_branco

        with mock.patch("coffee_break.ordem_bancaria.dados_da_ob", return_value=lidos):
            return self.client.post(
                reverse("coffee_break:anexar_ob", args=[self.principal.pk]),
                {"arquivo": SimpleUploadedFile("ob.pdf", _pdf_em_branco(), content_type="application/pdf")},
                follow=True,
            )

    def test_anexar_le_o_pdf_registra_a_data_e_copia_para_o_pagamento(self):
        from decimal import Decimal

        resposta = self._anexar({"numero": "2026OB000777", "data": dt.date(2026, 9, 25), "valor": Decimal("800.00")})
        self.assertContains(resposta, "Ordem bancária anexada")
        for s in (self.principal, self.outra):
            s.refresh_from_db()
            self.assertTrue(s.arquivo_ordem_bancaria)
            self.assertEqual(s.numero_ordem_bancaria, "2026OB000777")
            self.assertEqual(s.data_ordem_bancaria, dt.date(2026, 9, 25))
            self.assertTrue(s.historico.filter(descricao__icontains="ordem bancária").exists())
        self.assertEqual(services.avisos_da_ob(self.principal), [])
        tela = self.client.get(reverse("coffee_break:etapa_protocolo", args=[self.principal.pk]))
        self.assertContains(tela, "Enviar OB ao fornecedor")
        self.assertContains(tela, "Ordem bancária 2026OB000777")

    def test_valor_diferente_das_notas_avisa(self):
        from decimal import Decimal

        resposta = self._anexar({"numero": "", "data": None, "valor": Decimal("700.00")})
        self.assertContains(resposta, "não bate com o valor das notas fiscais")
        self.principal.refresh_from_db()
        self.assertEqual(self.principal.data_ordem_bancaria, timezone.localdate())

    def test_enviar_ob_manda_o_pdf_e_conclui_todas_as_os_do_pagamento(self):
        from decimal import Decimal

        self._anexar({"numero": "2026OB000777", "data": dt.date(2026, 9, 25), "valor": Decimal("800.00")})
        url = reverse("coffee_break:enviar_ob", args=[self.principal.pk])
        tela = self.client.get(url)
        self.assertIn("8957 e 8958", tela.context["valores"]["texto"])
        self.assertIn("2026OB000777", tela.context["valores"]["assunto"])
        resposta = self.client.post(url, {
            "para": "contato@favoemel.com.br", "copia": "", "assunto": "OB paga", "texto": "Segue a OB.",
        })
        self.assertRedirects(
            resposta, reverse("coffee_break:etapa_protocolo", args=[self.principal.pk]), fetch_redirect_response=False
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].attachments[0][0], "Ordem bancaria 2026OB000777.pdf")
        for s in (self.principal, self.outra):
            s.refresh_from_db()
            self.assertEqual(s.data_envio_empresa, timezone.localdate())
            self.assertTrue(s.concluida)
            self.assertTrue(
                s.historico.filter(acao=AcaoHistoricoCoffeeBreak.EMAIL, descricao__contains="contato@favoemel.com.br").exists()
            )

    def test_sem_ob_anexada_nao_envia(self):
        resposta = self.client.post(
            reverse("coffee_break:enviar_ob", args=[self.principal.pk]), {"para": "a@b.com", "assunto": "x"}
        )
        self.assertContains(resposta, "Anexe o PDF da ordem bancária")
        self.assertEqual(len(mail.outbox), 0)

    def test_remover_tira_de_todas_as_os(self):
        from decimal import Decimal

        self._anexar({"numero": "2026OB000777", "data": None, "valor": Decimal("800.00")})
        self.client.post(reverse("coffee_break:anexar_ob", args=[self.principal.pk]), {"acao": "remover"})
        for s in (self.principal, self.outra):
            s.refresh_from_db()
            self.assertFalse(s.arquivo_ordem_bancaria)
            self.assertEqual(s.numero_ordem_bancaria, "")
