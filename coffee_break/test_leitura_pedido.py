"""Regras de leitura do pedido de coffee break (`leitura_pedido`), sem banco."""

from datetime import time

from django.test import SimpleTestCase

from .leitura_pedido import (
    evento_do_texto,
    horario_do_texto,
    local_do_texto,
    quantidade_do_texto,
    quem_recebe_no_texto,
)


class QuantidadeTests(SimpleTestCase):
    def q(self, texto):
        achado = quantidade_do_texto(texto)
        return achado.valor if achado else None

    def test_por_extenso(self):
        self.assertEqual(self.q("coffee para quarenta pessoas"), 40)
        self.assertEqual(self.q("coffee break para vinte e cinco pessoas"), 25)
        self.assertEqual(self.q("Pessoas: 45 (quarenta e cinco)."), 45)

    def test_turmas_e_soma(self):
        self.assertEqual(self.q("Serão 2 turmas de 25 alunos."), 50)
        self.assertEqual(self.q("Serão 3 turmas de 15 no curso."), 45)
        self.assertEqual(self.q("coffee para 30 alunos + 10 instrutores"), 40)

    def test_faixa_cede_ao_pedido(self):
        self.assertEqual(self.q("Esperamos entre 40 e 50 pessoas. Pode mandar coffee para 30."), 30)
        self.assertEqual(self.q("Esperamos entre 40 e 50 pessoas."), 50)

    def test_correcao_vale_a_ultima(self):
        self.assertEqual(self.q("30 pessoas\n\ncorrigindo, serão 36 pessoas"), 36)
        self.assertEqual(self.q("Corrigindo: serão 55 pessoas, e não 40 como falei."), 55)
        self.assertEqual(self.q("Desconsiderar o pedido anterior (dia 14/10, 20 pessoas). Agora para 28 pessoas."), 28)

    def test_evento_passado_nao_conta(self):
        self.assertEqual(self.q("Como no evento do dia 10/09 (que foi para 25 pessoas), agora para 40 pessoas."), 40)

    def test_dois_lotes_vale_o_primeiro(self):
        self.assertEqual(self.q("1 coffee para 50 pessoas no dia 10 e outro para 20 no dia seguinte"), 50)

    def test_informal(self):
        self.assertEqual(self.q("coffee p 20 amanha 9h"), 20)
        self.assertEqual(self.q("pessoal da operação, uns 40"), 40)
        self.assertEqual(self.q("efetivo de 35 policiais"), 35)
        self.assertEqual(self.q("manda coffee p quarta, 25 pessoal"), 25)

    def test_nao_e_quantidade(self):
        self.assertIsNone(self.q("Ramal 1530, 3º andar, às 15h"))


class HorarioTests(SimpleTestCase):
    def h(self, texto):
        achado = horario_do_texto(texto)
        return achado.valor if achado else None

    def test_coffee_e_nao_o_curso(self):
        self.assertEqual(self.h("A palestra começa às 14h e o coffee será servido às 15h30."), time(15, 30))
        self.assertEqual(self.h("8h – abertura\n10h – coffee break\n12h – encerramento"), time(10, 0))

    def test_hora_seguida_de_numero_na_linha_de_baixo(self):
        self.assertEqual(self.h("Data: dia 06/10, às 15h\n30 participantes"), time(15, 0))

    def test_e_meia(self):
        self.assertEqual(self.h("dia 12/11 as 8 e meia da manha"), time(8, 30))


class EventoTests(SimpleTestCase):
    def e(self, texto):
        achado = evento_do_texto(texto)
        return achado.nome if achado else None

    def test_nome_no_corpo(self):
        self.assertEqual(self.e("coffee para a Reunião dos Delegados do Oeste na quinta-feira"), "Reunião dos Delegados do Oeste")
        self.assertEqual(self.e("para a Palestra de Educação\nno Trânsito, dia 17/11"), "Palestra de Educação no Trânsito")
        self.assertEqual(self.e("Evento: Workshop de Perícia Digital\nData: 08/12"), "Workshop de Perícia Digital")

    def test_sem_evento(self):
        self.assertIsNone(self.e("Dia 19/11, às 15h, no auditório da delegacia."))


class LocalTests(SimpleTestCase):
    def l(self, texto):
        achado = local_do_texto(texto)
        return achado.nome if achado else None

    def test_sem_o_endereco(self):
        self.assertEqual(self.l("Entrega: Escola Superior de Polícia Civil, Rua X, 2800"), "Escola Superior de Polícia Civil")
        self.assertEqual(self.l("Local: Base de apoio na Rodovia BR-277, km 80"), "Base de apoio")
        self.assertEqual(self.l("no pátio da Delegacia de Arapongas, Rua Garças, 1500"), "pátio da Delegacia de Arapongas")

    def test_quebra_de_linha_no_meio_do_nome(self):
        self.assertEqual(self.l("às 9h, na Câmara\nMunicipal de Laranjeiras do Sul."), "Câmara Municipal de Laranjeiras do Sul")

    def test_evento_nao_e_local(self):
        self.assertEqual(self.l("no Fórum Metropolitano, às 14h, no Auditório da Prefeitura, Av. Brasil, 1"), "Auditório da Prefeitura")


class QuemRecebeTests(SimpleTestCase):
    def r(self, texto):
        achado = quem_recebe_no_texto(texto)
        return achado.nome if achado else None

    def test_rotulos(self):
        self.assertIn("Cláudia Moretti", self.r("Recebimento: Agente Cláudia Moretti (43) 3322-4545."))
        self.assertIn("Toledo", self.r("Quem recebe é o inv. Toledo."))
        self.assertIn("Tiago Ramalho", self.r("Receber com o Investigador Tiago Ramalho."))
        self.assertIn("Gilmar Kuhn", self.r("O responsável no local será o Investigador Gilmar Kuhn."))

    def test_entregar_para(self):
        self.assertIn("Valdir", self.r("Entregar na portaria para o sr. Valdir."))

    def test_eu_recebo_e_quem_pede(self):
        self.assertTrue(quem_recebe_no_texto("70 pessoas, 17h\n\neu recebo").eh_quem_pede)
