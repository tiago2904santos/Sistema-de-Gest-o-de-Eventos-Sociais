from django.db import IntegrityError
from django.test import TestCase
from viagens_oficios.models import Justificativa
from viagens_oficios.models import ModeloJustificativa
from viagens_oficios.models import Oficio

class ModeloJustificativaModelTests(TestCase):

    def test_padrao_desmarca_anterior(self):
        a = ModeloJustificativa.objects.create(nome='MODELO A', texto='Um', is_padrao=True)
        self.assertTrue(ModeloJustificativa.objects.get(pk=a.pk).is_padrao)
        b = ModeloJustificativa.objects.create(nome='MODELO B', texto='Dois', is_padrao=True)
        a.refresh_from_db()
        self.assertFalse(a.is_padrao)
        self.assertTrue(b.is_padrao)

    def test_texto_normalizado(self):
        m = ModeloJustificativa.objects.create(nome='x', texto='  a  b  ')
        self.assertEqual(m.texto, 'a b')

class JustificativaModelTests(TestCase):

    def test_cria_vinculada_a_oficio(self):
        oficio = Oficio.objects.create(data_criacao='2026-05-10')
        j = Justificativa.objects.create(oficio=oficio, texto='Motivo')
        self.assertEqual(j.oficio_id, oficio.pk)

    def test_one_to_one_impede_duplicidade(self):
        oficio = Oficio.objects.create(data_criacao='2026-05-10')
        Justificativa.objects.create(oficio=oficio, texto='A')
        with self.assertRaises(IntegrityError):
            Justificativa.objects.create(oficio=oficio, texto='B')

    def test_str_sem_numero_oficio(self):
        oficio = Oficio.objects.create(data_criacao='2026-05-10')
        j = Justificativa.objects.create(oficio=oficio)
        self.assertEqual(str(j), 'Justificativa do Ofício —')

    def test_str_com_numero(self):
        oficio = Oficio.objects.create(numero=5, ano=2026, data_criacao='2026-05-10')
        j = Justificativa.objects.create(oficio=oficio)
        self.assertEqual(str(j), 'Justificativa do Ofício 05/2026')
