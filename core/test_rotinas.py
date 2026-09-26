"""Rotinas diárias sem cron (core/rotinas.py): uma vez por dia, no primeiro acesso."""

from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Setor
from cadastros.models import Estado, Municipio, OrgaoResponsavel, Regiao, TipoEvento
from core import rotinas
from core.models import Notificacao
from solicitacoes.models import SolicitacaoEvento, StatusSolicitacao

User = get_user_model()


class RodarSeForHoraTests(TestCase):
    def setUp(self):
        cache.clear()
        rotinas._ultimo_dia_visto = ""

    @mock.patch("core.rotinas.rodar")
    def test_roda_uma_vez_por_dia(self, rodar):
        hoje = date(2026, 9, 28)
        self.assertTrue(rotinas.rodar_se_for_hora(hoje))
        self.assertFalse(rotinas.rodar_se_for_hora(hoje))
        rotinas._ultimo_dia_visto = ""  # outro worker: a chave do cache segura
        self.assertFalse(rotinas.rodar_se_for_hora(hoje))
        self.assertTrue(rotinas.rodar_se_for_hora(hoje + timedelta(days=1)))
        self.assertEqual(rodar.call_count, 2)

    @mock.patch("core.rotinas.rodar_se_for_hora")
    def test_middleware_dispara_so_para_usuario_logado(self, disparar):
        usuario = User.objects.create_user("rotina", password="x")
        with override_settings(ROTINAS_DIARIAS_AUTOMATICAS=True):
            self.client.get(reverse("accounts:login"))
            self.assertEqual(disparar.call_count, 0)
            self.client.force_login(usuario)
            self.client.get(reverse("core:home"))
            self.assertEqual(disparar.call_count, 1)
        with override_settings(ROTINAS_DIARIAS_AUTOMATICAS=False):
            self.client.get(reverse("core:home"))
            self.assertEqual(disparar.call_count, 1)

    @mock.patch("core.rotinas.rodar_se_for_hora", side_effect=RuntimeError("boom"))
    def test_falha_da_rotina_nao_derruba_a_pagina(self, _disparar):
        self.client.force_login(User.objects.create_user("rotina2", password="x"))
        with override_settings(ROTINAS_DIARIAS_AUTOMATICAS=True), self.assertLogs("core.rotinas", level="ERROR"):
            self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)

    def test_rodar_protege_cada_rotina(self):
        with mock.patch("solicitacoes.lembretes.enviar_lembretes", side_effect=RuntimeError("x")), \
                mock.patch("viagens_prestacoes.avisos.avisar_prazos", return_value=0), \
                mock.patch("viagens_prestacoes.avisos.avisar_viagens", return_value=0), \
                mock.patch("core.rotinas.resumo_do_dia", return_value=0) as resumo, \
                self.assertLogs("core.rotinas", level="INFO") as registro:
            rotinas.rodar(date(2026, 9, 28))
        self.assertEqual(resumo.call_count, 1)
        self.assertTrue(any("falhou" in linha for linha in registro.output))


class ResumoDoDiaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ativo = User.objects.create_user("ativo", password="x")
        cls.ativo.setores.add(Setor.objects.get(sigla="ASCOM"))
        cls.inativo = User.objects.create_user("inativo", password="x")
        cls.sem_pendencia = User.objects.create_user("tranquilo", password="x")
        agora = timezone.now()
        User.objects.filter(pk__in=[cls.ativo.pk, cls.sem_pendencia.pk]).update(last_login=agora)
        User.objects.filter(pk=cls.inativo.pk).update(last_login=agora - timedelta(days=60))
        regiao = Regiao.objects.create(nome="Região R")
        municipio = Municipio.objects.create(nome="Cidade R", estado=Estado.objects.get(codigo_ibge=41), regiao=regiao)
        SolicitacaoEvento.objects.create(
            data_solicitacao=date(2026, 9, 20),
            data_inicio_evento=date(2026, 10, 1),
            data_fim_evento=date(2026, 10, 1),
            municipio=municipio,
            tipo_evento=TipoEvento.objects.create(nome="Ação R"),
            orgao_responsavel=OrgaoResponsavel.objects.create(nome="Órgão R"),
            solicitante_nome="Fulano",
            solicitante_cargo_unidade="Agente",
            contato="41 99999-0000",
            local_evento="Praça",
            status=StatusSolicitacao.AGUARDANDO_DESPACHO,
            criado_por=cls.ativo,
        )

    def test_resumo_so_para_quem_e_ativo_e_tem_pendencia_em_dia_util(self):
        segunda = date(2026, 9, 28)
        self.assertEqual(rotinas.resumo_do_dia(segunda), 1)
        aviso = Notificacao.objects.get(usuario=self.ativo)
        self.assertEqual(aviso.titulo, "Resumo de hoje (28/09): o que está pendente")
        self.assertIn("Eventos Sociais: 1 aguardando despacho, 1 evento em 7 dias", aviso.mensagem)
        self.assertEqual(aviso.link, reverse("core:home"))
        self.assertFalse(Notificacao.objects.filter(usuario__in=[self.inativo, self.sem_pendencia]).exists())
        # Rodar de novo no mesmo dia não repete.
        self.assertEqual(rotinas.resumo_do_dia(segunda), 0)

    def test_fim_de_semana_nao_tem_resumo(self):
        self.assertEqual(rotinas.resumo_do_dia(date(2026, 9, 27)), 0)
        self.assertFalse(Notificacao.objects.exists())
