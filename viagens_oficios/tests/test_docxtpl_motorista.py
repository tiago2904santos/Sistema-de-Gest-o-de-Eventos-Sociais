from django.test import TestCase
from viagens_cadastros.models import ConfiguracaoSistema
from viagens_cadastros.models import Servidor
from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context
from viagens_oficios.models import Oficio

class MotoristaDocxtplTests(TestCase):

    def setUp(self):
        ConfiguracaoSistema.get_singleton()

    def test_na_equipe_apenas_nome_formatado(self):
        motorista = Servidor.objects.create(nome='JOÃO DA SILVA')
        oficio = Oficio.objects.create(motorista=motorista, motorista_modo=Oficio.MOTORISTA_MODO_SERVIDOR)
        oficio.servidores.add(motorista)
        oficio.motorista_oficio_referencia = '99/2026'
        oficio.save(update_fields=['motorista_oficio_referencia'])
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertEqual(ctx['motorista_formatado'], 'João da Silva')
        self.assertNotIn('Ofício do Motorista', ctx['motorista_formatado'])

    def test_fora_da_equipe_com_referencias(self):
        motorista = Servidor.objects.create(nome='CARLOS EXTERNO')
        outro = Servidor.objects.create(nome='MARIA VIAJANTE')
        oficio = Oficio.objects.create(motorista=motorista, motorista_modo=Oficio.MOTORISTA_MODO_SERVIDOR, motorista_oficio_referencia='15/2026', motorista_protocolo_ref='123456789')
        oficio.servidores.add(outro)
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertIn('Carlos Externo', ctx['motorista_formatado'])
        self.assertIn('Ofício do Motorista: 15/2026', ctx['motorista_formatado'])
        self.assertIn('Protocolo do Motorista:', ctx['motorista_formatado'])
        self.assertIn('12.345.678-9', ctx['motorista_formatado'])

    def test_fora_da_equipe_sem_refs_so_nome(self):
        motorista = Servidor.objects.create(nome='PEDRO VOLANTE')
        outro = Servidor.objects.create(nome='OUTRO SERVIDOR MOTORISTA')
        oficio = Oficio.objects.create(motorista=motorista, motorista_modo=Oficio.MOTORISTA_MODO_SERVIDOR)
        oficio.servidores.add(outro)
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertEqual(ctx['motorista_formatado'], 'Pedro Volante')

    def test_manual_rotulos_capitalizados(self):
        oficio = Oficio.objects.create(motorista_modo=Oficio.MOTORISTA_MODO_MANUAL, motorista_manual_nome='ANA MANUAL', motorista_oficio_referencia='3/2026', motorista_protocolo_ref='987654321')
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertIn('Ana Manual', ctx['motorista_formatado'])
        self.assertIn('Ofício do Motorista:', ctx['motorista_formatado'])
        self.assertIn('Protocolo do Motorista:', ctx['motorista_formatado'])
