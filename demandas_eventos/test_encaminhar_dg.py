from datetime import date

from django.contrib.auth.models import Group
from django.urls import reverse

from cadastros.models import Estado, Municipio, Regiao, TipoEvento
from solicitacoes.models import AcaoHistorico, HistoricoSolicitacao, SolicitacaoEvento, StatusSolicitacao
from solicitacoes.permissions import GRUPO_GESTOR_DG
from solicitacoes.services import registrar_historico as registrar_historico_solicitacao

from .models import AcaoHistoricoDemanda, Palestrante, TipoEventoPalestra
from .tests import BaseDemandasTestCase, User


class EncaminharDGTests(BaseDemandasTestCase):
    def setUp(self):
        regiao = Regiao.objects.create(nome="Região Fictícia")
        self.municipio = Municipio.objects.create(
            nome="Cidade Fictícia", estado=Estado.objects.get(codigo_ibge=41), regiao=regiao
        )
        self.pcpr = TipoEvento.objects.get_or_create(nome="PCPR na Comunidade")[0]
        self.demanda = self.criar_demanda(
            evento=TipoEventoPalestra.PCPR_NA_COMUNIDADE,
            municipio=self.municipio,
            data_inicio_evento=date(2026, 11, 7),
            solicitante="Associação de Moradores Exemplo",
            telefone="(41) 99999-0000",
            descricao="Ação no bairro.",
            quantidade_publico=300,
        )
        self.demanda.palestrantes.add(Palestrante.objects.create(nome="Servidor Exemplo"))
        self.url = reverse("demandas_eventos:encaminhar_dg", args=[self.demanda.pk])

    def test_cria_rascunho_preenchido_e_liga_os_dois(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url)
        solicitacao = SolicitacaoEvento.objects.get()
        self.assertRedirects(resposta, reverse("solicitacoes:editar", args=[solicitacao.pk]), fetch_redirect_response=False)
        self.demanda.refresh_from_db()
        self.assertEqual(self.demanda.solicitacao_dg, solicitacao)
        self.assertEqual(solicitacao.status, StatusSolicitacao.RASCUNHO)
        self.assertEqual(solicitacao.criado_por, self.usuario)
        self.assertEqual(solicitacao.municipio, self.municipio)
        self.assertEqual((solicitacao.data_inicio_evento, solicitacao.data_fim_evento), (date(2026, 11, 7), date(2026, 11, 7)))
        self.assertEqual(solicitacao.tipo_evento, self.pcpr)
        self.assertEqual(solicitacao.solicitante_nome, "Associação de Moradores Exemplo")
        self.assertEqual(solicitacao.contato, "(41) 99999-0000")
        self.assertIn("Ação no bairro.", solicitacao.descricao_complementar)
        self.assertIn("Público previsto: 300 pessoas", solicitacao.descricao_complementar)
        self.assertIn(f"#{self.demanda.pk} da ASCOM", solicitacao.descricao_complementar)
        self.assertTrue(solicitacao.historico.filter(acao=AcaoHistorico.CRIACAO).exists())
        self.assertTrue(self.demanda.historico.filter(acao=AcaoHistoricoDemanda.ENCAMINHAMENTO_DG).exists())

        # Cada tela mostra a outra.
        resposta = self.client.get(reverse("demandas_eventos:editar", args=[self.demanda.pk]))
        self.assertContains(resposta, "Encaminhada à DG")
        self.assertContains(resposta, reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertNotContains(resposta, 'form="form-encaminhar-dg"')
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertContains(resposta, "Veio da ASCOM")
        self.assertContains(resposta, reverse("demandas_eventos:editar", args=[self.demanda.pk]))

    def test_nao_encaminha_duas_vezes(self):
        self.client.force_login(self.usuario)
        self.client.post(self.url)
        resposta = self.client.post(self.url, follow=True)
        self.assertContains(resposta, "Já encaminhada à DG")
        self.assertEqual(SolicitacaoEvento.objects.count(), 1)

    def test_so_post_e_so_quem_ve_a_palestra(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.force_login(self.outro)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertFalse(SolicitacaoEvento.objects.exists())

    def test_decisao_da_dg_volta_ao_historico_da_palestra(self):
        self.client.force_login(self.usuario)
        self.client.post(self.url)
        solicitacao = SolicitacaoEvento.objects.get()
        dg = User.objects.create_user("dg_exemplo", password="x")
        dg.groups.add(Group.objects.get_or_create(name=GRUPO_GESTOR_DG)[0])
        solicitacao.status = StatusSolicitacao.DEFERIDA_EM_ANDAMENTO
        solicitacao.save()
        registrar_historico_solicitacao(solicitacao, dg, AcaoHistorico.DECISAO, observacao="Equipe confirmada.")
        # Ação que não é da DG não vai para a palestra.
        registrar_historico_solicitacao(solicitacao, dg, AcaoHistorico.ATUALIZACAO)
        registros = self.demanda.historico.filter(acao=AcaoHistoricoDemanda.ANDAMENTO_DG)
        self.assertEqual(registros.count(), 1)
        self.assertIn("Deferida", registros.get().descricao)
        self.assertIn("Equipe confirmada.", registros.get().descricao)
        self.assertEqual(registros.get().usuario, dg)

    def test_solicitacao_sem_palestra_nao_gera_nada(self):
        solicitacao = SolicitacaoEvento.objects.create(criado_por=self.usuario)
        registrar_historico_solicitacao(solicitacao, self.usuario, AcaoHistorico.DECISAO)
        self.assertEqual(HistoricoSolicitacao.objects.count(), 1)
        self.assertFalse(self.demanda.historico.filter(acao=AcaoHistoricoDemanda.ANDAMENTO_DG).exists())
