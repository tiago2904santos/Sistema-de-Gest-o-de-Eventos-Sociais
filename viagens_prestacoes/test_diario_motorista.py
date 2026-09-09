from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
"""Troca do motorista do diário de bordo (Etapa 3), sem alterar o ofício."""
from django.contrib.auth import get_user_model
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_cadastros.models import Cargo
from viagens_cadastros.models import Servidor
from viagens_oficios.models import Oficio
from viagens_prestacoes.diario_services import build_diario_bordo_context
from viagens_prestacoes.diario_services import motorista_diario
from viagens_prestacoes.forms import DiarioMotoristaForm
from viagens_prestacoes.models import DiarioBordo
from viagens_roteiros.models import Roteiro
from viagens_roteiros.models import RoteiroTrecho

class DiarioMotoristaBaseTest(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='op', password='x')
        self.client.force_login(self.user)
        autorizar_viagens(self.user)
        self.cargo = Cargo.objects.create(nome='Agente')
        self.motorista_oficio = Servidor.objects.create(nome='Motorista Oficio', cargo=self.cargo, cpf='11122233344')
        self.servidor_equipe = Servidor.objects.create(nome='Servidor Equipe', cargo=self.cargo, cpf='55566677788')
        roteiro = Roteiro.objects.create()
        RoteiroTrecho.objects.create(roteiro=roteiro, sentido=RoteiroTrecho.Sentido.IDA, ordem=0)
        self.oficio = Oficio.objects.create(numero=7, ano=2026, protocolo='123456789', roteiro=roteiro, motorista=self.motorista_oficio, motorista_modo=Oficio.MOTORISTA_MODO_SERVIDOR)
        self.oficio.servidores.add(self.servidor_equipe)
        self.prestacao = self.oficio.prestacao_contas
        self.ps = self.prestacao.servidores_prestacao.get(servidor=self.servidor_equipe)
        self.diario = DiarioBordo.objects.create(prestacao=self.prestacao)

    def url(self):
        return reverse('viagens_prestacoes:diario_servidor_motorista', args=[self.ps.pk])

class MotoristaDiarioServiceTest(DiarioMotoristaBaseTest):

    def test_default_herda_motorista_do_oficio(self):
        self.assertEqual(self.diario.motorista_modo, DiarioBordo.MOTORISTA_MODO_OFICIO)
        nome, cpf = motorista_diario(self.diario)
        self.assertEqual(nome.upper(), 'MOTORISTA OFICIO')
        self.assertEqual(cpf, '111.222.333-44')
        self.assertFalse(self.diario.motorista_alterado)

    def test_modo_servidor_usa_servidor_da_equipe(self):
        self.diario.motorista_modo = DiarioBordo.MOTORISTA_MODO_SERVIDOR
        self.diario.motorista_servidor = self.servidor_equipe
        self.diario.save()
        nome, cpf = motorista_diario(self.diario)
        self.assertEqual(nome.upper(), 'SERVIDOR EQUIPE')
        self.assertEqual(cpf, '555.666.777-88')
        self.assertTrue(self.diario.motorista_alterado)

    def test_modo_outro_oficio_usa_dados_manuais_e_cabecalho(self):
        self.diario.motorista_modo = DiarioBordo.MOTORISTA_MODO_OUTRO
        self.diario.motorista_manual_nome = 'Fulano de Tal'
        self.diario.motorista_manual_cpf = '99988877766'
        self.diario.motorista_oficio_referencia = '15/2025'
        self.diario.motorista_protocolo_ref = '987654321'
        self.diario.save()
        nome, cpf = motorista_diario(self.diario)
        self.assertEqual(nome, 'Fulano de Tal')
        self.assertEqual(cpf, '999.888.777-66')
        header, _linhas = build_diario_bordo_context(self.diario)
        self.assertEqual(header['motorista'], 'FULANO DE TAL')
        self.assertEqual(header['cpf_motorista'], '999.888.777-66')
        self.assertEqual(header['oficio_motorista'], '15')
        self.assertEqual(header['ano'], '2025')
        self.assertEqual(header['protocolo_motorista'], '98.765.432-1')

    def test_modo_oficio_mantem_dados_do_oficio_no_cabecalho(self):
        header, _linhas = build_diario_bordo_context(self.diario)
        self.assertEqual(header['motorista'], 'MOTORISTA OFICIO')
        self.assertEqual(header['oficio_motorista'], '7')
        self.assertEqual(header['ano'], '2026')

class MotoristaFormTest(DiarioMotoristaBaseTest):

    def test_servidor_limitado_a_equipe_do_oficio(self):
        form = DiarioMotoristaForm(instance=self.diario, oficio=self.oficio)
        ids = set(form.fields['motorista_servidor'].queryset.values_list('pk', flat=True))
        self.assertEqual(ids, {self.servidor_equipe.pk})

    def test_servidor_obrigatorio_no_modo_servidor(self):
        form = DiarioMotoristaForm({'motorista_modo': DiarioBordo.MOTORISTA_MODO_SERVIDOR}, instance=self.diario, oficio=self.oficio)
        self.assertFalse(form.is_valid())
        self.assertIn('motorista_servidor', form.errors)

    def test_nome_obrigatorio_no_modo_outro(self):
        form = DiarioMotoristaForm({'motorista_modo': DiarioBordo.MOTORISTA_MODO_OUTRO, 'motorista_manual_nome': '  '}, instance=self.diario, oficio=self.oficio)
        self.assertFalse(form.is_valid())
        self.assertIn('motorista_manual_nome', form.errors)

    def test_voltar_para_oficio_limpa_overrides(self):
        self.diario.motorista_modo = DiarioBordo.MOTORISTA_MODO_OUTRO
        self.diario.motorista_manual_nome = 'Fulano'
        self.diario.motorista_manual_cpf = '99988877766'
        self.diario.save()
        form = DiarioMotoristaForm({'motorista_modo': DiarioBordo.MOTORISTA_MODO_OFICIO}, instance=self.diario, oficio=self.oficio)
        self.assertTrue(form.is_valid(), form.errors)
        diario = form.save()
        self.assertEqual(diario.motorista_manual_nome, '')
        self.assertEqual(diario.motorista_manual_cpf, '')

class MotoristaViewTest(DiarioMotoristaBaseTest):

    def test_get_renderiza_pagina(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Trocar motorista / viatura')
        self.assertContains(response, 'id="dmv-oficios-source"')
        self.assertNotContains(response, 'data-oficios=')

    def test_post_servidor_persiste_e_redireciona(self):
        response = self.client.post(self.url(), {'motorista_modo': DiarioBordo.MOTORISTA_MODO_SERVIDOR, 'motorista_servidor': str(self.servidor_equipe.pk)})
        self.assertRedirects(response, reverse('viagens_prestacoes:diario_servidor', args=[self.ps.pk]))
        self.diario.refresh_from_db()
        self.assertEqual(self.diario.motorista_modo, DiarioBordo.MOTORISTA_MODO_SERVIDOR)
        self.assertEqual(self.diario.motorista_servidor_id, self.servidor_equipe.pk)

    def test_post_outro_oficio_persiste_dados_manuais(self):
        response = self.client.post(self.url(), {'motorista_modo': DiarioBordo.MOTORISTA_MODO_OUTRO, 'motorista_manual_nome': 'Fulano de Tal', 'motorista_manual_cpf': '999.888.777-66', 'motorista_oficio_referencia': '15/2025', 'motorista_protocolo_ref': '98.765.432-1'})
        self.assertEqual(response.status_code, 302)
        self.diario.refresh_from_db()
        self.assertEqual(self.diario.motorista_modo, DiarioBordo.MOTORISTA_MODO_OUTRO)
        self.assertEqual(self.diario.motorista_manual_nome, 'Fulano de Tal')
        self.assertEqual(self.diario.motorista_manual_cpf, '99988877766')
        self.assertEqual(self.diario.motorista_protocolo_ref, '987654321')

    def test_oficio_original_nao_e_alterado(self):
        self.client.post(self.url(), {'motorista_modo': DiarioBordo.MOTORISTA_MODO_SERVIDOR, 'motorista_servidor': str(self.servidor_equipe.pk)})
        self.oficio.refresh_from_db()
        self.assertEqual(self.oficio.motorista_id, self.motorista_oficio.pk)
