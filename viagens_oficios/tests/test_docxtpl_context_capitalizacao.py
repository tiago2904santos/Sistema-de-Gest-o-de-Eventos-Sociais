from cadastros.models import Regiao
import datetime
from django.test import TestCase
from django.utils import timezone
from cadastros.models import Municipio as Cidade
from viagens_cadastros.models import ConfiguracaoSistema
from cadastros.models import Estado
from viagens_cadastros.models import Unidade
from viagens_oficios.docxtpl_context import build_justificativa_docxtpl_context
from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context
from viagens_oficios.models import Oficio
from viagens_roteiros.models import Roteiro
from viagens_roteiros.models import RoteiroDestino

class BuildOficioCapitalizacaoTests(TestCase):

    def setUp(self):
        ConfiguracaoSistema.get_singleton()

    def test_sem_roteiro_orgao_destino_legivel(self):
        oficio = Oficio.objects.create()
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertEqual(ctx['orgao_destino'], 'Gabinete do Delegado Geral Adjunto')
        self.assertIn(' do ', f" {ctx['orgao_destino']} ")

    def test_cabecalho_institucional_maiusculo_corpo_legivel(self):
        cfg = ConfiguracaoSistema.get_singleton()
        cfg.nome_orgao = 'DEPARTAMENTO DE POLÍCIA'
        cfg.unidade = Unidade.objects.create(nome='DELEGACIA REGIONAL DE POLÍCIA DE LONDRINA')
        cfg.save(update_fields=['nome_orgao', 'unidade'])
        oficio = Oficio.objects.create()
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertEqual(ctx['nome_orgao_cabecalho'], 'DEPARTAMENTO DE POLÍCIA')
        self.assertEqual(ctx['unidade_cabecalho'], 'DELEGACIA REGIONAL DE POLÍCIA DE LONDRINA')
        self.assertIn(' de ', f" {ctx['unidade']} ")
        self.assertIn(' de ', f" {ctx['nome_orgao']} ")

    def test_cabecalho_orgao_maiusculo_com_entrada_title_case(self):
        cfg = ConfiguracaoSistema.get_singleton()
        cfg.nome_orgao = 'Departamento de Polícia'
        cfg.unidade = Unidade.objects.create(nome='Delegacia Regional de Londrina')
        cfg.save(update_fields=['nome_orgao', 'unidade'])
        oficio = Oficio.objects.create()
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertEqual(ctx['nome_orgao_cabecalho'], 'DEPARTAMENTO DE POLÍCIA')
        self.assertEqual(ctx['unidade_cabecalho'], 'DELEGACIA REGIONAL DE LONDRINA')

    def test_justificativa_rodape_nao_todo_maiusculo(self):
        cfg = ConfiguracaoSistema.get_singleton()
        cfg.unidade = Unidade.objects.create(nome='ASSESSORIA DE COMUNICAÇÃO SOCIAL')
        cfg.logradouro = 'RUA EXEMPLO'
        cfg.numero = '1'
        cfg.bairro = 'BAIRRO'
        cfg.cidade_endereco = 'CURITIBA'
        cfg.uf = 'PR'
        cfg.cep = '80000000'
        cfg.telefone = '4133334444'
        cfg.email = 'TESTE@EX.COM'
        cfg.save()
        oficio = Oficio.objects.create()
        ctx = build_justificativa_docxtpl_context(oficio)
        self.assertIn('Assessoria de Comunicação Social', ctx['unidade_rodape'])
        self.assertNotEqual(ctx['unidade_rodape'].strip(), ctx['unidade_rodape'].upper())

    def test_oficio_contexto_usa_retorno_do_cabecalho_do_roteiro(self):
        estado = Estado.objects.get_or_create(sigla='PR', defaults={'nome':'Paraná', 'codigo_ibge':41})[0]
        sede = Cidade.objects.get_or_create(codigo_ibge=4106902, defaults={'nome':'Curitiba', 'estado':estado, 'regiao':Regiao.objects.get_or_create(nome='Interior')[0]})[0]
        destino = Cidade.objects.get_or_create(codigo_ibge=4113700, defaults={'nome':'Londrina', 'estado':estado, 'regiao':Regiao.objects.get_or_create(nome='Interior')[0]})[0]
        roteiro = Roteiro.objects.create(origem_municipio=sede, retorno_saida_dt=timezone.make_aware(datetime.datetime(2026, 7, 12, 18, 45), timezone.get_current_timezone()))
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=destino, ordem=1)
        oficio = Oficio.objects.create(roteiro=roteiro)
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertTrue(ctx['col_volta_saida'])
        self.assertIn('12/07/2026', ctx['col_volta_saida'])
        self.assertIn('18:45', ctx['col_volta_saida'])
