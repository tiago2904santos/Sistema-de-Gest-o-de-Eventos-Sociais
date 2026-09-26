"""Duplicar solicitação para eventos recorrentes (m017)."""

from django.urls import reverse
from django.utils import timezone

from . import services
from .models import AcaoHistorico, DecisaoDG, SolicitacaoEvento, StatusSolicitacao
from .tests import BaseSolicitacaoTestCase


class DuplicarTests(BaseSolicitacaoTestCase):
    def original(self):
        solicitacao = self.solicitacao_completa()
        solicitacao.itens_servico.create(servico=self.outro_servico)
        solicitacao.itens_equipe.create(equipe=self.outra_equipe, quantidade_servidores=3)
        SolicitacaoEvento.objects.filter(pk=solicitacao.pk).update(
            status=StatusSolicitacao.ATENDIDA,
            decisao_dg=DecisaoDG.ATENDER,
            observacoes_dg="Deferido",
            decidido_por=self.gestor,
            protocolo="12.345.678-9",
            unidade_movel=True,
            unidade_movel_designada=self.van,
            quantidade_cin=40,
        )
        solicitacao.refresh_from_db()
        return solicitacao

    def test_copia_dados_servicos_e_equipes_sem_datas_nem_decisao(self):
        original = self.original()
        self.client.force_login(self.solicitante)

        resposta = self.client.post(reverse("solicitacoes:duplicar", args=[original.pk]))

        nova = SolicitacaoEvento.objects.exclude(pk=original.pk).get()
        self.assertRedirects(
            resposta, reverse("solicitacoes:editar", args=[nova.pk]), fetch_redirect_response=False
        )
        self.assertEqual(nova.status, StatusSolicitacao.RASCUNHO)
        self.assertEqual(nova.criado_por, self.solicitante)
        self.assertEqual(nova.municipio, original.municipio)
        self.assertEqual(nova.tipo_evento, original.tipo_evento)
        self.assertEqual(nova.solicitante_nome, "Fulano")
        self.assertEqual(nova.unidade_movel_designada, self.van)
        self.assertEqual(nova.quantidade_cin, 40)
        self.assertIsNone(nova.data_inicio_evento)
        self.assertIsNone(nova.data_fim_evento)
        self.assertEqual(nova.data_solicitacao, timezone.localdate())
        self.assertEqual(nova.protocolo, "")
        self.assertEqual(nova.decisao_dg, DecisaoDG.PENDENTE)
        self.assertEqual(nova.observacoes_dg, "")
        self.assertIsNone(nova.decidido_por)
        self.assertEqual(
            set(nova.servicos.values_list("pk", flat=True)),
            {self.servico.pk, self.outro_servico.pk},
        )
        self.assertEqual(
            {i.equipe_id: i.quantidade_servidores for i in nova.itens_equipe.all()},
            {self.equipe.pk: 5, self.outra_equipe.pk: 3},
        )
        self.assertEqual(nova.quantidade_servidores, 8)
        self.assertFalse(nova.anexos.exists())
        criacao = nova.historico.get()
        self.assertEqual(criacao.acao, AcaoHistorico.CRIACAO)
        self.assertEqual(criacao.observacao, f"Copiada da #{original.pk}")

    def test_dg_duplica_e_fica_responsavel_pela_copia(self):
        original = self.original()
        nova = services.duplicar(original, self.gestor)
        self.assertEqual(nova.criado_por, self.gestor)

    def test_quem_nao_enxerga_nao_duplica(self):
        original = self.original()
        self.client.force_login(self.outro_solicitante)
        resposta = self.client.post(reverse("solicitacoes:duplicar", args=[original.pk]))
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(SolicitacaoEvento.objects.count(), 1)

    def test_so_por_post(self):
        original = self.original()
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:duplicar", args=[original.pk]))
        self.assertEqual(resposta.status_code, 405)

    def test_botao_na_lista_e_na_tela(self):
        original = self.original()
        self.client.force_login(self.solicitante)
        url = reverse("solicitacoes:duplicar", args=[original.pk])
        self.assertContains(self.client.get(reverse("solicitacoes:lista")), url)
        self.assertContains(
            self.client.get(reverse("solicitacoes:editar", args=[original.pk])), url
        )
