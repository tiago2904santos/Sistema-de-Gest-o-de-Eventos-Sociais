"""Assinar a agenda (m133): o feed iCalendar por token pessoal."""

from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from accounts.models import AssinaturaAgenda
from solicitacoes.tests import BaseSolicitacaoTestCase
from viagens_viagem.models import Viagem

from . import ics

User = get_user_model()


class FeedIcs(BaseSolicitacaoTestCase):
    def setUp(self):
        super().setUp()
        hoje = timezone.localdate()
        self.minha = self.criar_solicitacao(
            criado_por=self.solicitante,
            data_inicio_evento=hoje, data_fim_evento=hoje,
            solicitante_nome="Fulano Sigiloso", local_evento="Praça São José, 10",
        )
        self.de_outro = self.criar_solicitacao(criado_por=self.gestor, data_inicio_evento=hoje, data_fim_evento=hoje)
        self.assinatura = AssinaturaAgenda.gerar(self.solicitante)

    def _feed(self, token=None, **params):
        return self.client.get(reverse("agenda:ics", args=[token or self.assinatura.token]), params)

    def test_token_desconhecido_e_404_sem_login(self):
        self.assertEqual(self._feed("nao-existe").status_code, 404)

    def test_feed_sai_sem_login_com_as_permissoes_do_dono(self):
        resposta = self._feed()
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta["Content-Type"].startswith("text/calendar"))
        texto = resposta.content.decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR", texto)
        self.assertIn(f"UID:solicitacao-{self.minha.pk}@", texto)
        # A do gestor não é do solicitante: o token carrega a permissão dele.
        self.assertNotIn(f"UID:solicitacao-{self.de_outro.pk}@", texto)
        self.assertIn(reverse("solicitacoes:editar", args=[self.minha.pk]), texto)
        self.assertTrue(texto.endswith("END:VCALENDAR\r\n"))

    def test_feed_nao_leva_dados_pessoais(self):
        """Título, período, local e link — o nome do solicitante fica no sistema."""
        texto = self._feed().content.decode("utf-8")
        self.assertNotIn("Fulano Sigiloso", texto)
        self.assertNotIn("Praça São José", texto)
        self.assertIn("LOCATION:Cidade Teste", texto)

    def test_fim_exclusivo_e_dia_inteiro(self):
        s = self.criar_solicitacao(criado_por=self.solicitante, data_inicio_evento=date(2026, 9, 10), data_fim_evento=date(2026, 9, 11))
        texto = ics.feed(self.solicitante, dominio="t", base_url="http://t", hoje=date(2026, 9, 1))
        bloco = texto.split(f"UID:solicitacao-{s.pk}@t")[1].split("END:VEVENT")[0]
        self.assertIn("DTSTART;VALUE=DATE:20260910", bloco)
        self.assertIn("DTEND;VALUE=DATE:20260912", bloco)
        self.assertIn("BEGIN:VALARM", bloco)

    def test_fontes_e_meus_pela_query_string(self):
        root = User.objects.create_superuser("ics_root", "ics_root@example.com", None)
        Viagem.objects.create(
            titulo="V", destino_municipio=self.municipio, destino_estado=self.municipio.estado,
            data_inicio=timezone.localdate(), data_fim=timezone.localdate(),
        )
        token = AssinaturaAgenda.gerar(root).token
        tudo = self._feed(token).content.decode()
        self.assertIn("UID:viagem-", tudo)
        self.assertIn("UID:solicitacao-", tudo)
        so_viagens = self._feed(token, fontes="viagem").content.decode()
        self.assertIn("UID:viagem-", so_viagens)
        self.assertNotIn("UID:solicitacao-", so_viagens)
        # "Só a minha agenda": o root não criou nada, então nada é dele.
        meus = self._feed(token, meus="1").content.decode()
        self.assertNotIn("BEGIN:VEVENT", meus)

    def test_gerar_novo_link_invalida_o_anterior_e_revogar_apaga(self):
        antigo = self.assinatura.token
        self.client.force_login(self.solicitante)
        resposta = self.client.post(reverse("agenda:assinatura"), {"acao": "gerar"})
        self.assertEqual(resposta.status_code, 302)
        novo = AssinaturaAgenda.objects.get(usuario=self.solicitante).token
        self.assertNotEqual(antigo, novo)
        self.client.logout()
        self.assertEqual(self._feed(antigo).status_code, 404)
        self.assertEqual(self._feed(novo).status_code, 200)

        self.client.force_login(self.solicitante)
        self.client.post(reverse("agenda:assinatura"), {"acao": "revogar"})
        self.assertFalse(AssinaturaAgenda.objects.filter(usuario=self.solicitante).exists())
        self.client.logout()
        self.assertEqual(self._feed(novo).status_code, 404)

    def test_gerenciar_o_link_exige_login_e_post(self):
        resposta = self.client.post(reverse("agenda:assinatura"), {"acao": "gerar"})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("entrar", resposta["Location"])
        self.client.force_login(self.solicitante)
        self.assertEqual(self.client.get(reverse("agenda:assinatura")).status_code, 405)

    def test_usuario_inativo_nao_alimenta_o_feed(self):
        User.objects.filter(pk=self.solicitante.pk).update(is_active=False)
        self.assertEqual(self._feed().status_code, 404)

    def test_painel_mostra_o_modal_com_o_link(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("agenda:painel"))
        self.assertContains(resposta, reverse("agenda:ics", args=[self.assinatura.token]))
        self.assertContains(resposta, "Gerar novo link")


class FormatoRfc5545(BaseSolicitacaoTestCase):
    def test_linhas_longas_sao_dobradas_sem_partir_acento(self):
        titulo = "Operação São José dos Pinhais — " * 4
        texto = ics.calendario(
            [{"id": "x-1", "title": titulo, "start": "2026-09-10", "end": "2026-09-11", "extendedProps": {"fonte": "viagem", "url": "/v/1/"}}],
            nome="Agenda", dominio="t", base_url="http://t",
        )
        for linha in texto.split("\r\n"):
            self.assertLessEqual(len(linha.encode("utf-8")), 75, linha)
        # Desdobrando (CRLF + espaço), o título volta inteiro e escapado.
        desdobrado = texto.replace("\r\n ", "")
        self.assertIn("SUMMARY:" + titulo.replace(",", "\\,"), desdobrado)

    def test_virgula_e_ponto_e_virgula_escapados(self):
        self.assertEqual(ics._escapar("a, b; c\nd"), "a\\, b\\; c\\nd")
