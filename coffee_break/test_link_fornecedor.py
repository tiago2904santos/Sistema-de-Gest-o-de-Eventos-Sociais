"""m036: link seguro para o fornecedor enviar a nota fiscal e as certidões."""

import datetime as dt
import re
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Notificacao

from . import link_fornecedor
from .models import (
    CertidaoFornecedor,
    ContratoCoffeeBreak,
    EnvioFornecedor,
    HistoricoCoffeeBreak,
    LinkFornecedor,
    StatusEnvioFornecedor,
)
from .nota_fiscal import dados_no_texto
from .tests import BaseCoffeeBreakTestCase, _pdf_em_branco

DANFE = (
    "DANFE\nNº 000.008.957\nSÉRIE 001\nCHAVE DE ACESSO\n"
    "4126 0935 0147 1900 0166 5500 1000 0089 5715 7240 4356\n"
    "DATA DA EMISSÃO\n21/09/2026\nVALOR TOTAL DA NOTA\n842,80\n"
)
TRABALHISTA = (
    "CERTIDÃO NEGATIVA DE DÉBITOS TRABALHISTAS Nome: PADARIA E CONFEITARIA FAVO E MEL LTDA "
    "CNPJ: 35.014.719/0001-66 Validade: 15/02/2027 - 180 (cento e oitenta) dias"
)


def _arquivo(nome="doc.pdf", conteudo=None):
    return SimpleUploadedFile(nome, conteudo if conteudo is not None else _pdf_em_branco(), content_type="application/pdf")


class LinkFornecedorTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        cache.clear()
        ContratoCoffeeBreak.objects.filter(pk=self.contrato.pk).update(valor_unitario=Decimal("21.07"))
        self.solicitacao = self.criar_solicitacao(
            numero="41/2026", quantidade=40, valor_unitario=Decimal("21.07"),
            data_inicio_evento=dt.date(2026, 9, 20), local_entrega="1DP",
            responsavel_recebimento="Servidora Sintética da Silva",
        )

    def _gerar(self):
        link, token = link_fornecedor.gerar(self.solicitacao, self.ascom)
        return link, reverse("fornecedor_publico:envio", args=[token])

    def _enviar_nota(self, url, **extra):
        with mock.patch("coffee_break.nota_fiscal.numero_da_nota", return_value="8957"), \
                mock.patch("coffee_break.nota_fiscal.dados_da_nota", return_value=dados_no_texto(DANFE)):
            return self.client.post(url, {"tipo": "NOTA", "arquivo": _arquivo("nf.pdf"), **extra})

    def _enviar_certidao(self, url, texto=TRABALHISTA, tipo="TRABALHISTA"):
        with mock.patch("coffee_break.certidoes.texto_do_pdf", return_value=texto):
            return self.client.post(url, {"tipo": tipo, "arquivo": _arquivo("c.pdf"), "validade": ""})

    # -- Geração e envio por e-mail ------------------------------------------------

    def test_enviar_link_pelo_email_ao_fornecedor(self):
        self.client.force_login(self.ascom)
        url = reverse("coffee_break:enviar_link_fornecedor", args=[self.solicitacao.pk])
        tela = self.client.get(url)
        self.assertContains(tela, "{link}")
        self.assertFalse(LinkFornecedor.objects.exists())
        valores = tela.context["valores"]
        resposta = self.client.post(url, valores)
        self.assertEqual(resposta.status_code, 302)
        link = LinkFornecedor.objects.get()
        self.assertTrue(link.ativo)
        self.assertAlmostEqual(
            (link.expira_em - timezone.now()).total_seconds(), 30 * 86400, delta=120
        )
        self.assertEqual(len(mail.outbox), 1)
        corpo = mail.outbox[0].body
        token = re.search(r"/fornecedor/([A-Za-z0-9_-]+)/", corpo).group(1)
        self.assertGreaterEqual(len(token), 43)
        # O banco guarda só o hash; o histórico registra o envio sem o token.
        self.assertNotEqual(link.token_hash, token)
        self.assertEqual(link.token_hash, link_fornecedor.hash_do_token(token))
        self.assertFalse(HistoricoCoffeeBreak.objects.filter(descricao__contains=token).exists())
        self.assertTrue(HistoricoCoffeeBreak.objects.filter(descricao__icontains="link para envio").exists())

    def test_email_que_falha_nao_deixa_link(self):
        from smtplib import SMTPException

        self.client.force_login(self.ascom)
        url = reverse("coffee_break:enviar_link_fornecedor", args=[self.solicitacao.pk])
        valores = self.client.get(url).context["valores"]
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=SMTPException("fora")):
            resposta = self.client.post(url, valores)
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(LinkFornecedor.objects.exists())

    @override_settings(COFFEE_LINK_FORNECEDOR_DIAS=5)
    def test_validade_configuravel_e_novo_link_revoga_o_anterior(self):
        primeiro, url_antiga = self._gerar()
        self.assertAlmostEqual((primeiro.expira_em - timezone.now()).total_seconds(), 5 * 86400, delta=120)
        segundo, url_nova = self._gerar()
        primeiro.refresh_from_db()
        self.assertIsNotNone(primeiro.revogado_em)
        self.assertEqual(self.client.get(url_antiga).status_code, 404)
        self.assertEqual(self.client.get(url_nova).status_code, 200)

    # -- Página pública ------------------------------------------------------------

    def test_pagina_mostra_so_o_minimo(self):
        _, url = self._gerar()
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "41/2026")
        self.assertContains(resposta, "Evento de teste")
        self.assertContains(resposta, "20/09/2026")
        self.assertContains(resposta, "R$ 842,80")
        self.assertNotContains(resposta, "Servidora Sintética")
        self.assertNotContains(resposta, "1DP")
        self.assertNotContains(resposta, self.ascom.username)
        self.assertEqual(resposta["Referrer-Policy"], "no-referrer")

    def test_token_invalido_expirado_revogado(self):
        link, url = self._gerar()
        self.assertEqual(self.client.get(reverse("fornecedor_publico:envio", args=["x" * 43])).status_code, 404)
        self.assertEqual(self.client.get(reverse("fornecedor_publico:envio", args=["curto"])).status_code, 404)
        # O hash guardado não serve como token.
        self.assertEqual(self.client.get(reverse("fornecedor_publico:envio", args=[link.token_hash])).status_code, 404)
        LinkFornecedor.objects.filter(pk=link.pk).update(expira_em=timezone.now() - dt.timedelta(seconds=1))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self._enviar_nota(url).status_code, 404)
        LinkFornecedor.objects.filter(pk=link.pk).update(expira_em=timezone.now() + dt.timedelta(days=1))
        self.assertEqual(self.client.get(url).status_code, 200)
        link_fornecedor.revogar(LinkFornecedor.objects.get(pk=link.pk), self.ascom)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertFalse(EnvioFornecedor.objects.exists())

    def test_os_cancelada_invalida_o_link(self):
        _, url = self._gerar()
        self.solicitacao.cancelada = True
        self.solicitacao.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    @override_settings(COFFEE_LINK_LIMITE_INVALIDOS=3)
    def test_limite_de_tokens_invalidos_por_ip(self):
        _, url = self._gerar()
        for _ in range(3):
            self.client.get(reverse("fornecedor_publico:envio", args=["y" * 43]))
        # Bloqueado: nem o token certo responde a este IP por um tempo.
        self.assertEqual(self.client.get(url).status_code, 429)
        self.assertEqual(self.client.get(url, REMOTE_ADDR="10.0.0.8").status_code, 200)

    @override_settings(COFFEE_LINK_LIMITE_ENVIOS=2)
    def test_limite_de_envios(self):
        _, url = self._gerar()
        self._enviar_nota(url)
        self._enviar_nota(url)
        self.assertEqual(self._enviar_nota(url).status_code, 429)
        self.assertEqual(EnvioFornecedor.objects.count(), 2)

    def test_csrf_ativo_na_pagina_publica(self):
        from django.test import Client

        _, url = self._gerar()
        cliente = Client(enforce_csrf_checks=True)
        self.assertEqual(cliente.post(url, {"tipo": "NOTA", "arquivo": _arquivo()}).status_code, 403)

    # -- Recebimento e conferência ---------------------------------------------

    def test_nota_recebida_fica_aguardando_conferencia(self):
        link, url = self._gerar()
        resposta = self._enviar_nota(url)
        self.assertEqual(resposta.status_code, 302)
        envio = EnvioFornecedor.objects.get()
        self.assertEqual(envio.status, StatusEnvioFornecedor.RECEBIDO)
        self.assertEqual(envio.numero_nota, "8957")
        self.assertEqual(envio.valor_nota, Decimal("842.80"))
        # A OS não muda até a conferência.
        self.solicitacao.refresh_from_db()
        self.assertFalse(self.solicitacao.arquivo_nota_fiscal)
        self.assertEqual(self.solicitacao.numero_nota_fiscal, "")
        self.assertTrue(HistoricoCoffeeBreak.objects.filter(descricao__icontains="aguardando conferência").exists())
        self.assertTrue(Notificacao.objects.filter(usuario=self.ascom, titulo__icontains="41/2026").exists())
        # A confirmação aparece para o fornecedor.
        self.assertContains(self.client.get(url), "recebida")

    def test_conferencia_da_nota_aponta_divergencias(self):
        self.criar_solicitacao(numero="40/2026", numero_nota_fiscal="8957")
        _, url = self._gerar()
        self._enviar_nota(url)
        envio = EnvioFornecedor.objects.get()
        self.assertIn("já está na OS 40/2026", envio.avisos)

    def test_upload_invalido_e_recusado(self):
        _, url = self._gerar()
        resposta = self.client.post(url, {"tipo": "NOTA", "arquivo": _arquivo("nf.pdf", b"nao e pdf")})
        self.assertEqual(resposta.status_code, 400)
        resposta = self.client.post(url, {"tipo": "NOTA", "arquivo": SimpleUploadedFile("x.exe", b"MZ")})
        self.assertEqual(resposta.status_code, 400)
        resposta = self.client.post(url, {"tipo": "OUTRA", "arquivo": _arquivo()})
        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(EnvioFornecedor.objects.exists())

    def test_certidao_confere_tipo_cnpj_e_validade(self):
        _, url = self._gerar()
        outro = TRABALHISTA.replace("35.014.719/0001-66", "11.222.333/0001-81")
        self.assertContains(self._enviar_certidao(url, outro), "não é de PADARIA", status_code=400)
        self.assertContains(self._enviar_certidao(url, TRABALHISTA, "FGTS"), "não a FGTS", status_code=400)
        vencida = TRABALHISTA.replace("15/02/2027", "15/02/2026")
        self.assertContains(self._enviar_certidao(url, vencida), "venceu", status_code=400)
        self.assertFalse(EnvioFornecedor.objects.exists())
        self.assertEqual(self._enviar_certidao(url).status_code, 302)
        envio = EnvioFornecedor.objects.get()
        self.assertEqual(envio.validade_certidao, dt.date(2027, 2, 15))
        self.assertFalse(CertidaoFornecedor.objects.exists())

    def test_aceitar_leva_para_a_os_e_para_as_certidoes(self):
        _, url = self._gerar()
        self._enviar_nota(url)
        self._enviar_certidao(url)
        self.client.force_login(self.ascom)
        tela = self.client.get(reverse("coffee_break:etapa_nota", args=[self.solicitacao.pk]))
        self.assertContains(tela, "Recebido, aguardando conferência")
        for envio in EnvioFornecedor.objects.all():
            self.client.post(reverse("coffee_break:conferir_envio_fornecedor", args=[envio.pk]), {"acao": "aceitar"})
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.numero_nota_fiscal, "8957")
        self.assertTrue(self.solicitacao.arquivo_nota_fiscal)
        self.assertEqual(CertidaoFornecedor.objects.get().validade, dt.date(2027, 2, 15))
        self.assertFalse(EnvioFornecedor.objects.filter(status=StatusEnvioFornecedor.RECEBIDO).exists())
        # Aceitar de novo não duplica.
        envio = EnvioFornecedor.objects.filter(tipo="TRABALHISTA").get()
        self.client.post(reverse("coffee_break:conferir_envio_fornecedor", args=[envio.pk]), {"acao": "aceitar"})
        self.assertEqual(CertidaoFornecedor.objects.count(), 1)

    def test_recusar_registra_motivo(self):
        _, url = self._gerar()
        self._enviar_nota(url)
        envio = EnvioFornecedor.objects.get()
        self.client.force_login(self.ascom)
        self.client.post(
            reverse("coffee_break:conferir_envio_fornecedor", args=[envio.pk]),
            {"acao": "recusar", "motivo": "Nota de outra OS"},
        )
        envio.refresh_from_db()
        self.assertEqual(envio.status, StatusEnvioFornecedor.RECUSADO)
        self.assertTrue(HistoricoCoffeeBreak.objects.filter(descricao__icontains="Nota de outra OS").exists())
        self.solicitacao.refresh_from_db()
        self.assertFalse(self.solicitacao.arquivo_nota_fiscal)

    def test_revogar_pela_tela(self):
        link, url = self._gerar()
        self.client.force_login(self.ascom)
        self.client.post(reverse("coffee_break:revogar_link_fornecedor", args=[self.solicitacao.pk]))
        link.refresh_from_db()
        self.assertIsNotNone(link.revogado_em)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_anonimo_nao_acessa_as_telas_internas(self):
        link, url = self._gerar()
        self._enviar_nota(url)
        envio = EnvioFornecedor.objects.get()
        rotas_get = [
            reverse("coffee_break:enviar_link_fornecedor", args=[self.solicitacao.pk]),
            reverse("coffee_break:envio_fornecedor_arquivo", args=[envio.pk]),
            reverse("coffee_break:etapa_nota", args=[self.solicitacao.pk]),
            reverse("coffee_break:nota_fiscal", args=[self.solicitacao.pk]),
        ]
        for rota in rotas_get:
            resposta = self.client.get(rota)
            self.assertEqual(resposta.status_code, 302, rota)
            self.assertIn(reverse("accounts:login"), resposta["Location"])
        for rota in (
            reverse("coffee_break:conferir_envio_fornecedor", args=[envio.pk]),
            reverse("coffee_break:revogar_link_fornecedor", args=[self.solicitacao.pk]),
        ):
            self.assertEqual(self.client.post(rota, {"acao": "aceitar"}).status_code, 302)
        envio.refresh_from_db()
        link.refresh_from_db()
        self.assertEqual(envio.status, StatusEnvioFornecedor.RECEBIDO)
        self.assertIsNone(link.revogado_em)
        # Nem quem tem login, mas não o módulo.
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.client.get(rotas_get[1]).status_code, 403)
