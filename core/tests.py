from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from cadastros.models import (
    Equipe,
    Estado,
    Municipio,
    OrgaoResponsavel,
    Regiao,
    Servico,
    TipoEvento,
)
from core.models import Notificacao
from solicitacoes import services
from solicitacoes.models import DecisaoDG, SolicitacaoEvento, StatusSolicitacao
from solicitacoes.permissions import GRUPO_GESTOR_DG

User = get_user_model()


class NotificacoesWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.solicitante = User.objects.create_user(
            "solicitante", password="x", email="solicitante@pc.pr.gov.br"
        )
        cls.colega = User.objects.create_user(
            "colega", password="x", email="colega@pc.pr.gov.br"
        )
        cls.gestor = User.objects.create_user(
            "gestor", password="x", email="gestor@pc.pr.gov.br"
        )
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
        cls.solicitacao.itens_equipe.create(
            equipe=Equipe.objects.create(nome="Equipe Alfa"),
            quantidade_servidores=4,
        )

    def test_envio_notifica_gestores_dg(self):
        services.enviar(self.solicitacao, self.solicitante)
        notificacao = Notificacao.objects.get(usuario=self.gestor)
        self.assertIn("aguardando despacho", notificacao.titulo)
        self.assertIn(
            reverse("solicitacoes:detalhe", args=[self.solicitacao.pk]),
            notificacao.link,
        )
        # Só a DG recebe: nem o autor, nem os demais colegas.
        self.assertFalse(
            Notificacao.objects.filter(usuario=self.solicitante).exists()
        )
        self.assertFalse(Notificacao.objects.filter(usuario=self.colega).exists())

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
        self.assertIn("aguardando despacho", email.subject)
        self.assertIn(self.gestor.email, email.to)

    def test_usuario_inativo_nao_recebe(self):
        self.gestor.is_active = False
        self.gestor.save()
        services.enviar(self.solicitacao, self.solicitante)
        self.assertFalse(Notificacao.objects.filter(usuario=self.gestor).exists())


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
