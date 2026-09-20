import datetime as dt

from django.test import SimpleTestCase

from assistente import periodos


class InterpretacaoDePeriodo(SimpleTestCase):
    hoje = dt.date(2026, 3, 10)

    def test_mes_sem_ano_aponta_para_o_proximo_que_ainda_nao_passou(self):
        inicio, fim = periodos.interpretar("quem vai em setembro?", hoje=self.hoje)
        self.assertEqual(inicio, dt.date(2026, 9, 1))
        self.assertEqual(fim, dt.date(2026, 9, 30))

    def test_mes_ja_vencido_cai_no_ano_seguinte(self):
        inicio, _ = periodos.interpretar("em janeiro", hoje=self.hoje)
        self.assertEqual(inicio.year, 2027)

    def test_mes_com_ano_explicito_manda(self):
        inicio, fim = periodos.interpretar("setembro de 2024", hoje=self.hoje)
        self.assertEqual((inicio.year, fim.month), (2024, 9))

    def test_data_completa(self):
        inicio, fim = periodos.interpretar("evento dia 18/09/2026", hoje=self.hoje)
        self.assertEqual(inicio, dt.date(2026, 9, 18))
        self.assertEqual(inicio, fim)

    def test_intervalo_explicito(self):
        inicio, fim = periodos.interpretar("de 18/09 a 20/09", hoje=self.hoje)
        self.assertEqual(inicio, dt.date(2026, 9, 18))
        self.assertEqual(fim, dt.date(2026, 9, 20))

    def test_dia_solto_procura_o_proximo(self):
        inicio, _ = periodos.interpretar("dia 18", hoje=self.hoje)
        self.assertEqual(inicio, dt.date(2026, 3, 18))

    def test_dia_solto_ja_passado_vai_para_o_mes_seguinte(self):
        inicio, _ = periodos.interpretar("dia 5", hoje=self.hoje)
        self.assertEqual(inicio, dt.date(2026, 4, 5))

    def test_essa_semana(self):
        inicio, fim = periodos.interpretar("viagens dessa semana", hoje=self.hoje)
        self.assertEqual(inicio, dt.date(2026, 3, 9))  # segunda
        self.assertEqual(fim, dt.date(2026, 3, 15))

    def test_texto_sem_tempo_nao_inventa_data(self):
        self.assertEqual(periodos.interpretar("o que está pendente?"), (None, None))
