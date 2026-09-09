from django.test import TestCase
from viagens_cadastros.models import ConfiguracaoSistema
from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context
from viagens_oficios.models import Oficio

class RodapeOficioDocxtplTests(TestCase):

    def setUp(self):
        self.cfg = ConfiguracaoSistema.get_singleton()

    def test_email_minusculo(self):
        self.cfg.email = 'Contato@EXEMPLO.GOV.BR'
        self.cfg.save(update_fields=['email'])
        oficio = Oficio.objects.create()
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertEqual(ctx['email'], 'contato@exemplo.gov.br')

    def test_endereco_separador_traco_e_cidade_uf(self):
        self.cfg.logradouro = 'RUA DAS FLORES'
        self.cfg.numero = '100'
        self.cfg.bairro = 'CENTRO'
        self.cfg.cidade_endereco = 'LONDRINA'
        self.cfg.uf = 'pr'
        self.cfg.cep = '80010000'
        self.cfg.save(update_fields=['logradouro', 'numero', 'bairro', 'cidade_endereco', 'uf', 'cep'])
        oficio = Oficio.objects.create()
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertIn(' - ', ctx['endereco'])
        self.assertIn('Londrina/PR', ctx['endereco'])
