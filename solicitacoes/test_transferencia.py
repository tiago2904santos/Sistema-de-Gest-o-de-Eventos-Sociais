"""Transferir a solicitação para outro responsável (m014)."""

from django.contrib.auth.models import Group
from django.urls import reverse

from core.models import Notificacao

from . import permissions, services
from .models import AcaoHistorico, StatusSolicitacao
from .permissions import GRUPO_SOLICITANTE
from .tests import BaseSolicitacaoTestCase, User


class TransferenciaTests(BaseSolicitacaoTestCase):
    def transferir(self, usuario, solicitacao, novo, motivo=""):
        self.client.force_login(usuario)
        return self.client.post(
            reverse("solicitacoes:transferir", args=[solicitacao.pk]),
            {"responsavel": novo.pk if novo else "", "motivo_transferencia": motivo},
        )

    def test_responsavel_transfere_e_fica_no_historico(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)

        resposta = self.transferir(
            self.solicitante, solicitacao, self.outro_solicitante, "Férias"
        )

        # Quem passou adiante deixa de enxergar: volta para a lista.
        self.assertRedirects(resposta, reverse("solicitacoes:lista"), fetch_redirect_response=False)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.criado_por, self.outro_solicitante)
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        registro = solicitacao.historico.get(acao=AcaoHistorico.TRANSFERENCIA)
        self.assertEqual(registro.usuario, self.solicitante)
        self.assertEqual(registro.observacao, "Motivo: Férias")
        self.assertEqual(
            registro.alteracoes,
            [{"campo": "Responsável", "antes": "solicitante", "depois": "outro"}],
        )
        aviso = Notificacao.objects.get(usuario=self.outro_solicitante)
        self.assertIn("transferida para você", aviso.titulo)
        # O novo responsável passa a poder confirmar, editar etc.
        self.assertTrue(permissions.pode_reabrir(self.outro_solicitante, solicitacao))
        self.assertFalse(permissions.pode_reabrir(self.solicitante, solicitacao))

    def test_dg_transfere_e_o_antigo_responsavel_e_avisado(self):
        solicitacao = self.criar_solicitacao()
        resposta = self.transferir(self.gestor, solicitacao, self.outro_solicitante)
        self.assertRedirects(
            resposta,
            reverse("solicitacoes:editar", args=[solicitacao.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            Notificacao.objects.filter(usuario=self.solicitante, titulo__contains="transferida para").exists()
        )

    def test_quem_nao_enxerga_nao_transfere(self):
        solicitacao = self.criar_solicitacao()
        grupo, _ = Group.objects.get_or_create(name=GRUPO_SOLICITANTE)
        self.outro_solicitante.groups.add(grupo)
        resposta = self.transferir(self.outro_solicitante, solicitacao, self.outro_solicitante)
        self.assertEqual(resposta.status_code, 403)

    def test_exige_novo_responsavel_ativo_e_diferente(self):
        solicitacao = self.criar_solicitacao()
        inativo = User.objects.create_user("inativo", password="x", is_active=False)
        for novo in (None, inativo, self.solicitante):
            resposta = self.transferir(self.solicitante, solicitacao, novo)
            self.assertIn("#responsavel", resposta["Location"])
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.criado_por, self.solicitante)
        self.assertFalse(solicitacao.historico.filter(acao=AcaoHistorico.TRANSFERENCIA).exists())

    def test_encerrada_nao_transfere(self):
        solicitacao = self.criar_solicitacao(status=StatusSolicitacao.ATENDIDA)
        self.assertFalse(permissions.pode_transferir(self.gestor, solicitacao))

    def test_tela_mostra_o_responsavel_e_a_transferencia(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertContains(resposta, "Transferir para outro responsável")
        valores = [opcao["valor"] for opcao in resposta.context["responsaveis"]]
        self.assertNotIn(str(self.solicitante.pk), valores)
        self.assertIn(str(self.outro_solicitante.pk), valores)
