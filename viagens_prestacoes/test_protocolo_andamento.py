"""m105: em que setor o processo do ofício está no eProtocolo — lista, Etapa 3, rotina diária e aviso.

A integração responde em modo simulado (não é o eProtocolo de verdade): o dado
vem marcado como SIMULADO em toda tela.
"""
from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Notificacao
from integracoes.eprotocolo.exceptions import EProtocoloUnavailableError
from viagens_cadastros.models import ConfiguracaoSistema

from .models import PrestacaoContas
from .protocolo_services import atualizar_protocolos, consultar_protocolo_da_prestacao, prestacoes_para_consultar
from .test_helpers import PrestacaoFixturesMixin, PrestacaoTestCase as TestCase


class AndamentoDoProtocoloTests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=105)
        self.prestacao = self.fixture.prestacao

    def test_consulta_guarda_setor_situacao_e_marca_simulado(self):
        resultado = consultar_protocolo_da_prestacao(self.prestacao)
        self.assertTrue(resultado.ok)
        self.assertTrue(resultado.simulado)
        self.prestacao.refresh_from_db()
        self.assertEqual(self.prestacao.protocolo_local, "Local de Trâmite (simulado)")
        self.assertEqual(self.prestacao.protocolo_situacao, "Em tramitacao")
        self.assertIsNotNone(self.prestacao.protocolo_consultado_em)
        self.assertIsNotNone(self.prestacao.protocolo_movimentado_em)
        self.assertTrue(self.prestacao.protocolo_simulado)

    def test_sem_protocolo_nao_consulta(self):
        oficio = self.prestacao.oficio
        oficio.protocolo = ""
        oficio.save(update_fields=["protocolo"])
        resultado = consultar_protocolo_da_prestacao(self.prestacao)
        self.assertIn("ainda não tem número de protocolo", resultado.erro)
        self.assertNotIn(self.prestacao, prestacoes_para_consultar())

    def test_falha_do_eprotocolo_vira_erro_sem_derrubar(self):
        with mock.patch("integracoes.eprotocolo.services.consultar_protocolo", side_effect=EProtocoloUnavailableError()):
            resultado = consultar_protocolo_da_prestacao(self.prestacao)
        self.assertIn("Não foi possível consultar o eProtocolo agora", resultado.erro)
        self.prestacao.refresh_from_db()
        self.assertIsNone(self.prestacao.protocolo_consultado_em)

    def test_rotina_diaria_consulta_uma_vez_por_dia_so_as_em_aberto(self):
        finalizada = self.criar_prestacao(numero=106, finalizada=True)
        self.assertEqual(atualizar_protocolos(), 1)
        self.assertEqual(atualizar_protocolos(), 0)
        self.prestacao.refresh_from_db()
        finalizada.prestacao.refresh_from_db()
        self.assertIsNotNone(self.prestacao.protocolo_consultado_em)
        self.assertIsNone(finalizada.prestacao.protocolo_consultado_em)
        # No dia seguinte consulta de novo.
        PrestacaoContas.objects.filter(pk=self.prestacao.pk).update(protocolo_consultado_em=timezone.now() - timedelta(days=1))
        self.assertEqual(atualizar_protocolos(), 1)

    def test_rodar_das_rotinas_chama_a_atualizacao(self):
        from core import rotinas

        with mock.patch("viagens_prestacoes.protocolo_services.atualizar_protocolos", return_value=0) as atualizar, \
                mock.patch("solicitacoes.lembretes.enviar_lembretes", return_value=0), \
                mock.patch("viagens_prestacoes.avisos.avisar_prazos", return_value=0), \
                mock.patch("viagens_prestacoes.avisos.avisar_viagens", return_value=0), \
                mock.patch("core.rotinas.resumo_do_dia", return_value=0):
            rotinas.rodar(timezone.localdate())
        self.assertEqual(atualizar.call_count, 1)

    def test_aviso_no_sino_quando_o_processo_chega_ao_setor_do_despacho(self):
        config = ConfiguracaoSistema.get_singleton()
        config.setor_despacho_eprotocolo = "local de tramite"
        config.save()
        resultado = consultar_protocolo_da_prestacao(self.prestacao)
        self.assertTrue(resultado.avisou)
        aviso = Notificacao.objects.get(usuario=self.user)
        self.assertIn("chegou em Local de Trâmite (simulado)", aviso.titulo)
        self.assertIn("(simulado)", aviso.titulo)
        self.assertIn("importe-o na prestação", aviso.mensagem)
        # Consultar de novo não repete o aviso.
        self.assertFalse(consultar_protocolo_da_prestacao(self.prestacao).avisou)
        self.assertEqual(Notificacao.objects.filter(usuario=self.user).count(), 1)

    def test_sem_setor_configurado_ou_outro_setor_nao_avisa(self):
        self.assertFalse(consultar_protocolo_da_prestacao(self.prestacao).avisou)
        config = ConfiguracaoSistema.get_singleton()
        config.setor_despacho_eprotocolo = "DAF/DP"
        config.save()
        self.assertFalse(consultar_protocolo_da_prestacao(self.prestacao).avisou)
        self.assertEqual(Notificacao.objects.count(), 0)

    def test_lista_mostra_o_setor_com_simulado_e_o_botao_atualizar(self):
        resposta = self.get_listagem()
        self.assertContains(resposta, "ainda não consultado")
        url = reverse("viagens_prestacoes:prestacao_protocolo_atualizar", args=[self.prestacao.pk])
        self.assertContains(resposta, url)
        self.assertEqual(self.client.get(url).status_code, 405)
        resposta = self.client.post(url, {"next": reverse("viagens_prestacoes:index")}, follow=True)
        self.assertContains(resposta, "Processo em Local de Trâmite (simulado)")
        self.assertContains(resposta, "Consulta SIMULADA")
        self.assertContains(resposta, "SIMULADO")
        grupo = resposta.context["grupos"][0]
        self.assertEqual(grupo["protocolo"]["local"], "Local de Trâmite (simulado)")
        self.assertTrue(grupo["protocolo"]["simulado"])
        self.assertTrue(grupo["protocolo"]["desde"])

    def test_etapa_3_mostra_o_andamento(self):
        consultar_protocolo_da_prestacao(self.prestacao)
        ps = self.fixture.prestacoes_servidor[0]
        resposta = self.client.get(reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk]))
        self.assertContains(resposta, "data-protocolo-andamento")
        self.assertContains(resposta, "Local de Trâmite (simulado)")
        self.assertContains(resposta, "SIMULADO")

    def test_configuracao_aceita_o_setor_do_despacho(self):
        from django.contrib.auth.models import Group

        self.user.groups.add(Group.objects.get(name="VIAGENS_GESTOR"))
        resposta = self.client.get(reverse("viagens_oficios:institucional"))
        self.assertContains(resposta, 'name="setor_despacho_eprotocolo"')
