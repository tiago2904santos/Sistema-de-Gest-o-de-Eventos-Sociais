from django.test import TestCase
from viagens_oficios.models import ModeloMotivoOficio
from viagens_oficios.models import Oficio

class OficioModelTests(TestCase):

    def test_cria_oficio_minimo(self):
        oficio = Oficio.objects.create()
        self.assertIsNotNone(oficio.pk)

    def test_numero_formatado_funciona(self):
        oficio = Oficio.objects.create(numero=1, ano=2026)
        self.assertEqual(oficio.numero_formatado, '01/2026')

    def test_str_funciona(self):
        oficio = Oficio.objects.create(numero=12, ano=2026)
        self.assertEqual(str(oficio), 'Ofício 12/2026')

    def test_status_default_rascunho(self):
        oficio = Oficio.objects.create()
        self.assertEqual(oficio.status, Oficio.STATUS_RASCUNHO)

    def test_modelo_motivo_normaliza_nome(self):
        modelo = ModeloMotivoOficio.objects.create(nome='   padrão equipe  ', texto=' Texto base ')
        self.assertEqual(modelo.nome, 'PADRÃO EQUIPE')
