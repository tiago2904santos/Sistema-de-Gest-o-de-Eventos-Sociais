"""Feriados nacionais calculados, os locais cadastrados e a soma de dias úteis (m094)."""

import datetime

from django.test import TestCase

from core import feriados
from core.models import Feriado

D = datetime.date


class FeriadosTests(TestCase):
    def setUp(self):
        feriados.limpar_cache()
        self.addCleanup(feriados.limpar_cache)

    def test_moveis_de_2026(self):
        nacionais = feriados.feriados_nacionais(2026)
        self.assertEqual(feriados.pascoa(2026), D(2026, 4, 5))
        for data in (D(2026, 2, 16), D(2026, 2, 17), D(2026, 4, 3), D(2026, 6, 4)):
            self.assertIn(data, nacionais)
        self.assertIn(D(2026, 9, 7), nacionais)

    def test_somar_pula_fim_de_semana_e_feriado_nacional(self):
        # Sexta 04/09/2026; segunda 07/09 é feriado: 08, 09, 10.
        self.assertEqual(feriados.somar_dias_uteis(D(2026, 9, 4), 3), D(2026, 9, 10))

    def test_feriado_local_cadastrado_conta(self):
        Feriado.objects.create(data=D(2020, 9, 8), nome="Padroeira da cidade", anual=True)
        self.assertEqual(feriados.somar_dias_uteis(D(2026, 9, 4), 3), D(2026, 9, 11))
        Feriado.objects.create(data=D(2026, 9, 9), nome="Ponto facultativo", anual=False)
        self.assertEqual(feriados.somar_dias_uteis(D(2026, 9, 4), 3), D(2026, 9, 14))
        self.assertFalse(feriados.eh_dia_util(D(2027, 9, 8)) and D(2027, 9, 8).weekday() < 5)

    def test_dias_uteis_entre(self):
        self.assertEqual(feriados.dias_uteis_entre(D(2026, 9, 4), D(2026, 9, 10)), 3)
        self.assertEqual(feriados.dias_uteis_entre(D(2026, 9, 10), D(2026, 9, 4)), -3)
