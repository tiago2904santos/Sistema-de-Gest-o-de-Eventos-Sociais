from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Estado, Municipio, OrgaoResponsavel, Regiao, Servico, TipoEvento
from core.models import Notificacao
from solicitacoes import services
from solicitacoes.models import DecisaoDG, SolicitacaoEvento, StatusSolicitacao
from solicitacoes.permissions import GRUPO_ANALISTA, GRUPO_GESTOR_DG

User = get_user_model()


class NotificacoesWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.solicitante = User.objects.create_user(
            "solicitante", password="x", email="solicitante@pc.pr.gov.br"
        )
        cls.analista = User.objects.create_user(
            "analista", password="x", email="analista@pc.pr.gov.br"
        )
        cls.analista.groups.add(Group.objects.create(name=GRUPO_ANALISTA))
        cls.gestor = User.objects.create_user("gestor", password="x")
        cls.gestor.groups.add(Group.objects.create(name=GRUPO_GESTOR_DG))

        regiao = Regiao.objects.create(nome="Região")
        estado = Estado.objects.get(codigo_ibge=41)
        municipio = Municipio.objects.create(
            nome="Cidade", estado=estado, regiao=regiao
        )
        cls.solicitacao = SolicitacaoEvento.objects.create(
            data_solicitacao=date(2026, 8, 1),
            data_inicio_evento=date(2026, 9, 10),
            data_fim_evento=date(2026, 9, 11),
            municipio=municipio,
            tipo_evento=TipoEvento.objects.create(nome="Ação social"),
            orgao_responsavel=OrgaoResponsavel.objects.create(nome="Órgão"),
            solicitante_nome="Fulano",
            solicitante_cargo_unidade="Agente / Unidade",
            contato="41 99999-0000",
            local_evento="Praça",
            criado_por=cls.solicitante,
        )
        cls.solicitacao.itens_servico.create(
            servico=Servico.objects.create(nome="Emissão de CIN")
        )

    def test_envio_notifica_analistas(self):
        services.enviar(self.solicitacao, self.solicitante)
        notificacao = Notificacao.objects.get(usuario=self.analista)
        self.assertIn("aguardando análise", notificacao.titulo)
        self.assertIn(
            reverse("solicitacoes:analisar", args=[self.solicitacao.pk]),
            notificacao.link,
        )

    def test_encaminhamento_notifica_gestores_e_solicitante(self):
        from cadastros.models import Equipe

        self.solicitacao.status = StatusSolicitacao.EM_ANALISE
        self.solicitacao.itens_equipe.create(
            equipe=Equipe.objects.create(nome="Alfa"), quantidade_servidores=4
        )
        self.solicitacao.tipo_operacao = "DIARIA"
        self.solicitacao.save()
        services.encaminhar_para_despacho(self.solicitacao, self.analista)
        self.assertTrue(
            Notificacao.objects.filter(
                usuario=self.gestor, titulo__icontains="aguardando despacho"
            ).exists()
        )
        self.assertTrue(
            Notificacao.objects.filter(
                usuario=self.solicitante, titulo__icontains="encaminhada"
            ).exists()
        )

    def test_decisao_notifica_solicitante(self):
        self.solicitacao.status = StatusSolicitacao.AGUARDANDO_DESPACHO
        self.solicitacao.save()
        services.despachar(
            self.solicitacao, self.gestor, DecisaoDG.NAO_ATENDER, "Sem equipe."
        )
        notificacao = Notificacao.objects.get(usuario=self.solicitante)
        self.assertIn("não atendida", notificacao.titulo)
        self.assertEqual(notificacao.mensagem, "Sem equipe.")

    def test_email_enviado_para_quem_tem_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            services.enviar(self.solicitacao, self.solicitante)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("aguardando análise", email.subject)
        self.assertIn(self.analista.email, email.to)

    def test_usuario_inativo_nao_recebe(self):
        self.analista.is_active = False
        self.analista.save()
        services.enviar(self.solicitacao, self.solicitante)
        self.assertFalse(Notificacao.objects.filter(usuario=self.analista).exists())


class CentralNotificacoesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user("fulano", password="x")

    def test_pagina_marca_como_lidas(self):
        Notificacao.objects.create(usuario=self.usuario, titulo="Aviso 1")
        Notificacao.objects.create(usuario=self.usuario, titulo="Aviso 2")
        self.client.force_login(self.usuario)

        resposta = self.client.get(reverse("core:notificacoes"))
        self.assertContains(resposta, "Aviso 1")
        self.assertContains(resposta, "Aviso 2")
        self.assertEqual(
            self.usuario.notificacoes.filter(lida=False).count(), 0
        )

    def test_contador_no_cabecalho(self):
        Notificacao.objects.create(usuario=self.usuario, titulo="Aviso")
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("dashboard:index"))
        self.assertContains(resposta, "top-header__sino-contador")

    def test_notificacoes_sao_do_proprio_usuario(self):
        outro = User.objects.create_user("outro", password="x")
        Notificacao.objects.create(usuario=outro, titulo="Segredo do outro")
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("core:notificacoes"))
        self.assertNotContains(resposta, "Segredo do outro")
