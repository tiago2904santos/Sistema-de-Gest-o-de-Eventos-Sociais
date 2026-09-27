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

    def test_feriados_no_periodo_e_o_municipal_so_para_a_cidade(self):
        """m138: nacionais e gerais para todos; o municipal só quando a cidade é pedida,
        e nunca na conta de dias úteis da casa."""
        from cadastros.models import Estado, Municipio, Regiao

        pr = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        maringa = Municipio.objects.create(nome="Maringá Feriado", estado=pr, regiao=Regiao.objects.create(nome="R"))
        Feriado.objects.create(data=D(2020, 12, 19), nome="Emancipação política do Paraná", anual=True)
        Feriado.objects.create(data=D(2026, 5, 10), nome="Aniversário de Maringá", anual=True, municipio=maringa)

        geral = feriados.feriados_no_periodo(D(2026, 5, 1), D(2026, 12, 31))
        nomes = {f["nome"] for f in geral}
        self.assertIn("Corpus Christi", nomes)
        self.assertIn("Emancipação política do Paraná", nomes)
        self.assertNotIn("Aniversário de Maringá", nomes)
        self.assertEqual([f["data"] for f in geral if f["nome"] == "Emancipação política do Paraná"], [D(2026, 12, 19)])

        com_cidade = feriados.feriados_no_periodo(D(2026, 5, 2), D(2026, 5, 31), municipios=[maringa])
        self.assertEqual([(f["data"], f["municipio"]) for f in com_cidade], [(D(2026, 5, 10), "Maringá Feriado")])

        # Segunda 11/05/2026 é dia útil da casa: o feriado de Maringá (domingo 10/05) não pula nada.
        self.assertEqual(feriados.somar_dias_uteis(D(2026, 5, 8), 1), D(2026, 5, 11))
        Feriado.objects.create(data=D(2026, 5, 11), nome="Só em Maringá", anual=False, municipio=maringa)
        feriados.limpar_cache()
        self.assertEqual(feriados.somar_dias_uteis(D(2026, 5, 8), 1), D(2026, 5, 11))

    def test_feriado_local_cadastrado_conta(self):
        Feriado.objects.create(data=D(2020, 9, 8), nome="Padroeira da cidade", anual=True)
        self.assertEqual(feriados.somar_dias_uteis(D(2026, 9, 4), 3), D(2026, 9, 11))
        Feriado.objects.create(data=D(2026, 9, 9), nome="Ponto facultativo", anual=False)
        self.assertEqual(feriados.somar_dias_uteis(D(2026, 9, 4), 3), D(2026, 9, 14))
        self.assertFalse(feriados.eh_dia_util(D(2027, 9, 8)) and D(2027, 9, 8).weekday() < 5)

    def test_dias_uteis_entre(self):
        self.assertEqual(feriados.dias_uteis_entre(D(2026, 9, 4), D(2026, 9, 10)), 3)
        self.assertEqual(feriados.dias_uteis_entre(D(2026, 9, 10), D(2026, 9, 4)), -3)
