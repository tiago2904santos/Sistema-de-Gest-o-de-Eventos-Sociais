from datetime import date, datetime, time, timezone

from django.test import SimpleTestCase

from core.leitura.datas import (
    data_hora_de_cabecalho,
    datas_do_texto,
    dobrar,
    horarios_do_texto,
    prazo_do_texto,
    quando_do_evento,
    turno_do_texto,
)
from demandas_eventos.horarios import extrair_horarios

# Sexta-feira: a data do e-mail nos exemplos de mapas/demandas.md §3.E.
REFERENCIA = date(2026, 9, 25)


class DobrarTests(SimpleTestCase):
    def test_mantem_o_comprimento_para_as_posicoes_valerem_no_original(self):
        original = "Solicitação – 1º de março às 14h"
        dobrado = dobrar(original)
        self.assertEqual(len(dobrado), len(original))
        self.assertEqual(dobrado, "solicitacao - 1o de marco as 14h")


class TabelaDoLevantamentoTests(SimpleTestCase):
    """Os casos medidos no levantamento (mapas/demandas.md §3.E)."""

    def quando(self, texto):
        resultado = quando_do_evento(texto, REFERENCIA)
        self.assertIsNotNone(resultado, texto)
        return resultado

    def test_dia_com_hora(self):
        q = self.quando("Solicitamos palestra no dia 15/10 às 14h na Escola Estadual X")
        self.assertEqual((q.inicio, q.fim, q.hora_inicio), (date(2026, 10, 15), None, time(14, 0)))
        self.assertEqual(q.confianca, "A")

    def test_periodo_com_faixa_de_horario(self):
        q = self.quando("evento de 20 a 22 de novembro de 2026, das 9h às 12h")
        self.assertEqual((q.inicio, q.fim), (date(2026, 11, 20), date(2026, 11, 22)))
        self.assertEqual((q.hora_inicio, q.hora_fim), (time(9, 0), time(12, 0)))
        self.assertEqual(len(q.dias), 3)

    def test_ordinal_por_extenso(self):
        q = self.quando("1º de dezembro às 19h30")
        self.assertEqual((q.inicio, q.hora_inicio), (date(2026, 12, 1), time(19, 30)))

    def test_data_com_pontos_e_ano_curto(self):
        q = self.quando("Data: 05.01.27 - 08h")
        self.assertEqual((q.inicio, q.hora_inicio), (date(2027, 1, 5), time(8, 0)))

    def test_sem_ano_mais_de_60_dias_antes_e_do_ano_seguinte(self):
        self.assertEqual(self.quando("em 12/03").inicio, date(2027, 3, 12))
        self.assertEqual(self.quando("em 10/08").inicio, date(2026, 8, 10))

    def test_proxima_terca_pela_manha(self):
        q = self.quando("na próxima terça pela manhã")
        self.assertEqual(q.inicio, date(2026, 9, 29))
        self.assertIsNone(q.hora_inicio)
        self.assertEqual(q.turno, "manhã")

    def test_amanha_com_hora(self):
        q = self.quando("reunião amanhã 10:00")
        self.assertEqual((q.inicio, q.hora_inicio), (date(2026, 9, 26), time(10, 0)))


class ArmadilhasTests(SimpleTestCase):
    def test_relativa_se_resolve_contra_a_data_do_email_e_nao_contra_hoje(self):
        q = quando_do_evento("pode ser amanhã?", date(2026, 1, 10))
        self.assertEqual(q.inicio, date(2026, 1, 11))

    def test_referencia_com_fuso_vale_o_dia_local(self):
        # 01h UTC do dia 26 ainda é dia 25 em Brasília.
        referencia = datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(quando_do_evento("amanhã", referencia).inicio, date(2026, 9, 26))

    def test_dia_da_semana_colado_a_data_absoluta_e_so_rotulo(self):
        itens = datas_do_texto("quinta-feira, 24 de setembro de 2026, às 10 horas", REFERENCIA)
        self.assertEqual([(i.tipo, i.inicio) for i in itens], [("data", date(2026, 9, 24))])
        itens = datas_do_texto("no sábado (03/10) e 03/10 (sábado)", REFERENCIA)
        self.assertTrue(all(i.tipo == "data" for i in itens))

    def test_entre_os_dias_e_periodo(self):
        item = datas_do_texto("entre os dias 20 e 22 de novembro", REFERENCIA)[0]
        self.assertEqual((item.tipo, item.inicio, item.fim, len(item.dias)), ("periodo", date(2026, 11, 20), date(2026, 11, 22), 3))

    def test_lista_de_dias_nao_e_periodo(self):
        item = datas_do_texto("dias 20, 21 e 23/11", REFERENCIA)[0]
        self.assertEqual(item.tipo, "lista")
        self.assertEqual(item.dias, (date(2026, 11, 20), date(2026, 11, 21), date(2026, 11, 23)))

    def test_periodo_entre_meses(self):
        item = datas_do_texto("de 30 de outubro a 2 de novembro", REFERENCIA)[0]
        self.assertEqual((item.tipo, item.inicio, item.fim), ("periodo", date(2026, 10, 30), date(2026, 11, 2)))
        item = datas_do_texto("de 30/10 a 02/11", REFERENCIA)[0]
        self.assertEqual((item.inicio, item.fim), (date(2026, 10, 30), date(2026, 11, 2)))

    def test_numero_de_documento_cpf_e_valor_nao_viram_data(self):
        texto = (
            "Ofício nº 05/10 enviado. Lei 13.709/18. CPF 123.456.789-00, R$ 1.500,00, "
            "fone 3322-1100, 10.5 km, hoje em dia"
        )
        self.assertEqual(datas_do_texto(texto, REFERENCIA), [])

    def test_palavra_terminada_em_no_nao_e_numero_de_documento(self):
        item = datas_do_texto("início 13/10, término 15/10", REFERENCIA)[-1]
        self.assertEqual(item.inicio, date(2026, 10, 15))

    def test_expediente_de_segunda_a_sexta_nao_e_data(self):
        texto = "Atendemos de segunda a sexta, das 8h às 18h. A palestra será na terça, 06/10."
        q = quando_do_evento(texto, REFERENCIA)
        self.assertEqual(q.inicio, date(2026, 10, 6))
        self.assertEqual([i.tipo for i in datas_do_texto(texto, REFERENCIA)], ["data"])

    def test_ordinal_nao_e_dia_da_semana(self):
        self.assertEqual(datas_do_texto("na segunda edição, a quinta turma", REFERENCIA), [])

    def test_semana_que_vem(self):
        q = quando_do_evento("semana que vem, quinta, às 15 hs", REFERENCIA)
        self.assertEqual((q.inicio, q.hora_inicio), (date(2026, 10, 1), time(15, 0)))

    def test_prazo_perde_para_a_data_do_evento(self):
        q = quando_do_evento("Responder até o dia 30/09. O evento será em 15/10.", REFERENCIA)
        self.assertEqual(q.inicio, date(2026, 10, 15))

    def test_faixa_que_comeca_com_hora_sem_h(self):
        q = quando_do_evento("Pedimos palestra no dia 20/10, das 9 às 12h.", REFERENCIA)
        self.assertEqual((q.hora_inicio, q.hora_fim), (time(9, 0), time(12, 0)))


class HorariosTests(SimpleTestCase):
    def horas(self, texto):
        return [(h.inicio, h.fim) for h in horarios_do_texto(texto)]

    def test_formatos(self):
        self.assertEqual(self.horas("14h"), [(time(14, 0), None)])
        self.assertEqual(self.horas("14h30"), [(time(14, 30), None)])
        self.assertEqual(self.horas("às 14:30"), [(time(14, 30), None)])
        self.assertEqual(self.horas("às 10 horas"), [(time(10, 0), None)])
        self.assertEqual(self.horas("às 10."), [(time(10, 0), None)])
        self.assertEqual(self.horas("às 2 da tarde"), [(time(14, 0), None)])
        self.assertEqual(self.horas("ao meio-dia"), [(time(12, 0), None)])

    def test_faixas(self):
        self.assertEqual(self.horas("das 9h às 12h"), [(time(9, 0), time(12, 0))])
        self.assertEqual(self.horas("das 9 às 12h"), [(time(9, 0), time(12, 0))])
        self.assertEqual(self.horas("14:00 às 16:00"), [(time(14, 0), time(16, 0))])
        self.assertEqual(self.horas("das 8h ao meio-dia"), [(time(8, 0), time(12, 0))])

    def test_duracao_nao_e_horario(self):
        self.assertEqual(self.horas("palestra de 2 horas"), [])
        self.assertEqual(self.horas("carga horária de 4 horas"), [])
        self.assertEqual(self.horas("duração de 1h30"), [])
        self.assertEqual(self.horas("para as 10 pessoas da turma"), [])

    def test_turno(self):
        self.assertEqual(turno_do_texto("Boa tarde! Pode ser pela manhã?"), "manhã")
        self.assertEqual(turno_do_texto("Boa noite, respondo mais tarde"), "")
        self.assertEqual(turno_do_texto("no período vespertino"), "tarde")


class PrazoTests(SimpleTestCase):
    def test_ate_as_17h_de_hoje(self):
        prazo = prazo_do_texto("Preciso do posicionamento até às 17h de hoje.", REFERENCIA)
        self.assertEqual((prazo.data, prazo.hora), (REFERENCIA, time(17, 0)))

    def test_deadline_amanha(self):
        prazo = prazo_do_texto("deadline amanhã às 12h", REFERENCIA)
        self.assertEqual((prazo.data, prazo.hora), (date(2026, 9, 26), time(12, 0)))

    def test_sem_prazo(self):
        self.assertIsNone(prazo_do_texto("Evento no dia 15/10.", REFERENCIA))


class CabecalhoTests(SimpleTestCase):
    def test_formatos_de_cabecalho(self):
        esperado = datetime(2026, 9, 24, 14, 32)
        for valor in (
            "quinta-feira, 24 de setembro de 2026 14:32",
            "Thursday, September 24, 2026 2:32 PM",
            "qui., 24 de set. de 2026 às 14:32",
            "24/09/2026 14:32",
            "Thu, Sep 24, 2026 at 2:32 PM",
        ):
            with self.subTest(valor=valor):
                self.assertEqual(data_hora_de_cabecalho(valor), esperado)

    def test_formato_do_protocolo_tem_fuso(self):
        valor = data_hora_de_cabecalho("Thu, 24 Sep 2026 14:32:00 -0300")
        self.assertEqual(valor.utcoffset().total_seconds(), -3 * 3600)

    def test_meia_noite_em_ingles(self):
        self.assertEqual(data_hora_de_cabecalho("Sep 24, 2026 12:05 AM"), datetime(2026, 9, 24, 0, 5))

    def test_invalido(self):
        self.assertIsNone(data_hora_de_cabecalho("sem data"))


class ExtrairHorariosDaPlanilhaTests(SimpleTestCase):
    """Correção em demandas_eventos/horarios.py: "das 9h às 12h" sobrava "das às"."""

    def test_faixa_com_dois_conectores_nao_deixa_sobra(self):
        self.assertEqual(extrair_horarios("das 9h às 12h"), (time(9, 0), time(12, 0), ""))

    def test_recado_continua_na_sobra(self):
        self.assertEqual(extrair_horarios("10h00 às 15h00 à definir"), (time(10, 0), time(15, 0), "à definir"))
