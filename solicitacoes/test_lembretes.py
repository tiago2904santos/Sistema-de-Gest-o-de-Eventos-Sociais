"""Fila "Confirmar atendimento" e lembretes automáticos (m007)."""

from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from core.models import Notificacao

from .lembretes import enviar_lembretes
from .models import (
    AcaoHistorico,
    DecisaoDG,
    LembreteSolicitacao,
    StatusSolicitacao,
    TipoLembrete,
)
from .tests import BaseSolicitacaoTestCase


class BaseLembretes(BaseSolicitacaoTestCase):
    def setUp(self):
        self.hoje = timezone.localdate()

    def deferida(self, fim_ha_dias=1, **kwargs):
        fim = self.hoje - timedelta(days=fim_ha_dias)
        return self.criar_solicitacao(
            status=StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
            decisao_dg=DecisaoDG.ATENDER,
            data_solicitacao=fim - timedelta(days=20),
            data_inicio_evento=fim - timedelta(days=1),
            data_fim_evento=fim,
            **kwargs,
        )


class FilaConfirmarAtendimentoTests(BaseLembretes):
    def test_fila_mostra_so_deferidas_com_evento_encerrado(self):
        encerrada = self.deferida()
        self.deferida(fim_ha_dias=-5)  # evento ainda por vir
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:lista"), {"fila": "confirmar"})
        self.assertEqual(
            [linha["solicitacao"].pk for linha in resposta.context["linhas"]],
            [encerrada.pk],
        )
        fila = next(
            item for item in resposta.context["situacoes"] if item["slug"] == "confirmar"
        )
        self.assertEqual(fila["total"], 1)
        self.assertContains(resposta, "Confirmar atendimento")


class EnviarLembretesTests(BaseLembretes):
    def test_autor_recebe_aviso_para_confirmar_uma_vez_so(self):
        self.solicitante.email = "autor@exemplo.test"
        self.solicitante.save()
        solicitacao = self.deferida()

        with self.captureOnCommitCallbacks(execute=True):
            enviados = enviar_lembretes()
        self.assertEqual(enviados[TipoLembrete.CONFIRMAR_ATENDIMENTO], 1)
        aviso = Notificacao.objects.get(usuario=self.solicitante)
        self.assertIn("confirme o atendimento", aviso.titulo)
        self.assertTrue(aviso.link.endswith("#encerramento"))
        self.assertEqual(len(mail.outbox), 1)

        # Rodar de novo não repete.
        self.assertEqual(enviar_lembretes()[TipoLembrete.CONFIRMAR_ATENDIMENTO], 0)
        self.assertEqual(Notificacao.objects.filter(usuario=self.solicitante).count(), 1)
        self.assertTrue(
            LembreteSolicitacao.objects.filter(
                solicitacao=solicitacao, tipo=TipoLembrete.CONFIRMAR_ATENDIMENTO
            ).exists()
        )

    def test_evento_antigo_nao_vira_enxurrada(self):
        self.deferida(fim_ha_dias=90)
        self.assertEqual(enviar_lembretes()[TipoLembrete.CONFIRMAR_ATENDIMENTO], 0)

    def test_evento_de_hoje_ainda_nao_avisa(self):
        self.deferida(fim_ha_dias=0)
        self.assertEqual(enviar_lembretes()[TipoLembrete.CONFIRMAR_ATENDIMENTO], 0)

    def test_dg_avisada_de_despacho_com_evento_proximo(self):
        self.criar_solicitacao(
            status=StatusSolicitacao.AGUARDANDO_DESPACHO,
            data_solicitacao=self.hoje - timedelta(days=5),
            data_inicio_evento=self.hoje + timedelta(days=3),
            data_fim_evento=self.hoje + timedelta(days=3),
        )
        self.criar_solicitacao(
            status=StatusSolicitacao.AGUARDANDO_DESPACHO,
            data_solicitacao=self.hoje,
            data_inicio_evento=self.hoje + timedelta(days=20),
            data_fim_evento=self.hoje + timedelta(days=20),
        )
        enviados = enviar_lembretes()
        self.assertEqual(enviados[TipoLembrete.DESPACHO_PROXIMO], 1)
        aviso = Notificacao.objects.get(usuario=self.gestor)
        self.assertIn("evento em 3 dias", aviso.titulo)
        self.assertEqual(enviar_lembretes()[TipoLembrete.DESPACHO_PROXIMO], 0)

    def test_devolucao_parada_avisa_o_autor(self):
        solicitacao = self.criar_solicitacao(status=StatusSolicitacao.DEVOLVIDA)
        registro = solicitacao.historico.create(
            usuario=self.gestor, acao=AcaoHistorico.DEVOLUCAO, observacao="Ajuste"
        )
        type(registro).objects.filter(pk=registro.pk).update(
            criado_em=timezone.now() - timedelta(days=5)
        )
        recente = self.criar_solicitacao(status=StatusSolicitacao.DEVOLVIDA)
        recente.historico.create(
            usuario=self.gestor, acao=AcaoHistorico.DEVOLUCAO, observacao="Ajuste"
        )
        enviados = enviar_lembretes()
        self.assertEqual(enviados[TipoLembrete.DEVOLUCAO_PARADA], 1)
        aviso = Notificacao.objects.get(usuario=self.solicitante)
        self.assertEqual(aviso.solicitacao, solicitacao)

    def test_simular_nao_grava(self):
        self.deferida()
        saida = StringIO()
        call_command("enviar_lembretes_solicitacoes", "--simular", stdout=saida)
        self.assertIn("seriam enviados", saida.getvalue())
        self.assertFalse(LembreteSolicitacao.objects.exists())
        self.assertFalse(Notificacao.objects.exists())

    def test_comando_envia(self):
        self.deferida()
        saida = StringIO()
        call_command("enviar_lembretes_solicitacoes", stdout=saida)
        self.assertIn("Total: 1 enviados", saida.getvalue())
        self.assertEqual(LembreteSolicitacao.objects.count(), 1)
