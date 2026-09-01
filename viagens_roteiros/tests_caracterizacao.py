"""Demonstrativos do sistema oficial de diárias, reproduzidos ao centavo.

Estes casos vêm de telas do **sistema oficial de solicitação de diárias** — o
demonstrativo com os valores que a administração efetivamente paga. Eles não
descrevem o que este código faz: descrevem o que a administração paga. Se um
deles quebrar, o defeito é aqui, não no teste.

São a régua exigida pelo plano da unificação antes de qualquer mudança no
cálculo (dinheiro não muda sem caracterização), e vieram junto com o motor
portado da Central de Viagens 3, onde foram levantados.

Diferença em relação à origem: lá os valores vinham de uma tabela fixa no
código quando não havia vigência cadastrada. Aqui a vigência é obrigatória,
então cada teste semeia a tabela com os mesmos valores oficiais — o que exercita
o caminho real, e não um atalho que só existe em teste.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.test import TestCase

from viagens_cadastros.models import TabelaDiaria

from .services.diarias import (
    CAPITAIS_POR_UF,
    Marcador,
    RoteiroIncalculavel,
    SemTabelaDeDiarias,
    _decompor,
    calcular_diarias,
    classificar_faixa,
)

# Os valores do demonstrativo oficial usado como régua.
VALOR_INTERIOR = Decimal("290.55")
VALOR_CAPITAL = Decimal("371.26")
VALOR_BRASILIA = Decimal("468.12")

SAO_PAULO = ("SAO PAULO", "SP")
ABATIA = ("ABATIA", "PR")
FLORIANOPOLIS = ("FLORIANOPOLIS", "SC")
ADRIANOPOLIS = ("ADRIANOPOLIS", "PR")
CURITIBA = ("CURITIBA", "PR")


def marcador(saida, chegada, destino):
    return Marcador(
        saida=saida,
        chegada=chegada,
        destino_cidade=destino[0],
        destino_uf=destino[1],
    )


class BaseDiariasTestCase(TestCase):
    """Semeia a vigência com os valores do demonstrativo oficial."""

    @classmethod
    def setUpTestData(cls):
        for faixa, valor in (
            (TabelaDiaria.Faixa.INTERIOR, VALOR_INTERIOR),
            (TabelaDiaria.Faixa.CAPITAL, VALOR_CAPITAL),
            (TabelaDiaria.Faixa.BRASILIA, VALOR_BRASILIA),
        ):
            TabelaDiaria.objects.create(
                faixa=faixa, vigencia_inicio=date(2026, 1, 1), valor_24h=valor
            )

    def calcular(self, marcadores, chegada_final, servidores=1):
        return calcular_diarias(
            marcadores,
            chegada_final,
            quantidade_servidores=servidores,
            sede_cidade="CURITIBA",
            sede_uf="PR",
        )


class DemonstrativoOficialTests(BaseDiariasTestCase):
    """Cada teste reproduz um demonstrativo oficial, linha a linha."""

    def test_curitiba_sao_paulo_abatia_curitiba_da_773_19(self):
        """Demonstrativo oficial: total R$ 773,19.

        | Trecho | Grupo    | Período                 | Dias/Horas  | Diária    |
        |--------|----------|-------------------------|-------------|-----------|
        | 1      | Capitais | 12/08 08:00–13/08 18:00 | 1 dia + 10h | R$ 482,64 |
        | 2      | Demais   | 13/08 18:00–14/08 18:00 | 1 dia       | R$ 290,55 |

        As 10 horas do trecho 1 são o deslocamento São Paulo → Abatiá, faturado
        na tarifa da **capital**, de onde o servidor saiu.
        """
        resultado = self.calcular(
            [
                marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO),
                marcador(datetime(2026, 8, 13, 8, 0), datetime(2026, 8, 13, 18, 0), ABATIA),
                marcador(datetime(2026, 8, 14, 8, 0), datetime(2026, 8, 14, 18, 0), CURITIBA),
            ],
            datetime(2026, 8, 14, 18, 0),
        )
        self.assertEqual(resultado["totais"]["total_valor_decimal"], Decimal("773.19"))

    def test_o_mesmo_roteiro_conferido_trecho_a_trecho(self):
        """O total certo pode esconder trechos errados; aqui cada linha é afirmada."""
        resultado = self.calcular(
            [
                marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO),
                marcador(datetime(2026, 8, 13, 8, 0), datetime(2026, 8, 13, 18, 0), ABATIA),
                marcador(datetime(2026, 8, 14, 8, 0), datetime(2026, 8, 14, 18, 0), CURITIBA),
            ],
            datetime(2026, 8, 14, 18, 0),
        )
        trechos = resultado["trechos"]
        self.assertEqual(len(trechos), 2)

        capital, interior = trechos
        self.assertEqual(capital["tipo"], "CAPITAL")
        self.assertEqual(capital["data_saida"], "12/08/2026")
        self.assertEqual(capital["hora_saida"], "08:00")
        self.assertEqual(capital["data_chegada"], "13/08/2026")
        self.assertEqual(capital["hora_chegada"], "18:00")
        self.assertEqual(capital["n_diarias"], 1)
        self.assertEqual(capital["percentual_adicional"], 30)
        self.assertEqual(capital["subtotal"], "482,64")

        self.assertEqual(interior["tipo"], "INTERIOR")
        self.assertEqual(interior["data_saida"], "13/08/2026")
        self.assertEqual(interior["hora_saida"], "18:00")
        self.assertEqual(interior["n_diarias"], 1)
        self.assertEqual(interior["percentual_adicional"], 0)
        self.assertEqual(interior["subtotal"], "290,55")

    def test_retorno_passando_pela_capital_da_1144_45(self):
        """Demonstrativo oficial: total R$ 1.144,45.

        A mesma cidade aparece duas vezes, em trechos separados, e cada
        passagem é faturada por si.
        """
        resultado = self.calcular(
            [
                marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO),
                marcador(datetime(2026, 8, 13, 8, 0), datetime(2026, 8, 13, 18, 0), ABATIA),
                marcador(datetime(2026, 8, 14, 8, 0), datetime(2026, 8, 14, 18, 0), SAO_PAULO),
                marcador(datetime(2026, 8, 15, 8, 0), datetime(2026, 8, 15, 18, 0), CURITIBA),
            ],
            datetime(2026, 8, 15, 18, 0),
        )
        self.assertEqual(resultado["totais"]["total_valor_decimal"], Decimal("1144.45"))
        self.assertEqual(
            [t["tipo"] for t in resultado["trechos"]],
            ["CAPITAL", "INTERIOR", "CAPITAL"],
        )

    def test_destinos_seguidos_do_mesmo_grupo_formam_um_trecho_so(self):
        """Demonstrativo oficial: total R$ 1.169,47, num **único** trecho.

        São Paulo, Florianópolis e São Paulo — três destinos, um trecho. As
        sobras isoladas (6h, 2h, 0h) não chegariam a 6 horas e nenhuma geraria
        complemento sozinha; somadas dentro do trecho dão 8h e valem 15%.
        """
        resultado = self.calcular(
            [
                marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO),
                marcador(datetime(2026, 8, 13, 8, 0), datetime(2026, 8, 13, 14, 0), FLORIANOPOLIS),
                marcador(datetime(2026, 8, 14, 8, 0), datetime(2026, 8, 14, 16, 0), SAO_PAULO),
                marcador(datetime(2026, 8, 15, 8, 0), datetime(2026, 8, 15, 16, 0), CURITIBA),
            ],
            datetime(2026, 8, 15, 16, 0),
        )
        self.assertEqual(resultado["totais"]["total_valor_decimal"], Decimal("1169.47"))
        self.assertEqual(len(resultado["trechos"]), 1)

        trecho = resultado["trechos"][0]
        self.assertEqual(trecho["tipo"], "CAPITAL")
        self.assertEqual(trecho["data_saida"], "12/08/2026")
        self.assertEqual(trecho["hora_saida"], "08:00")
        self.assertEqual(trecho["data_chegada"], "15/08/2026")
        self.assertEqual(trecho["hora_chegada"], "16:00")
        self.assertEqual(trecho["n_diarias"], 3)
        self.assertEqual(trecho["percentual_adicional"], 15)

    def test_o_deslocamento_entre_destinos_nao_desaparece_da_conta(self):
        """São 10 horas de estrada entre São Paulo e Abatiá; têm de ser cobradas."""
        resultado = self.calcular(
            [
                marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO),
                marcador(datetime(2026, 8, 13, 8, 0), datetime(2026, 8, 13, 18, 0), ABATIA),
                marcador(datetime(2026, 8, 14, 8, 0), datetime(2026, 8, 14, 18, 0), CURITIBA),
            ],
            datetime(2026, 8, 14, 18, 0),
        )
        complementos = [
            t["percentual_adicional"]
            for t in resultado["trechos"]
            if t["percentual_adicional"]
        ]
        self.assertEqual(complementos, [30])


class EscadaDoRestoTests(BaseDiariasTestCase):
    """Quanto vale o tempo que sobra depois dos dias inteiros.

    A escada vem de cinco demonstrativos oficiais, um deles um experimento que
    isola a variável: 12h01 **dentro do mesmo dia**, sem virada de meia-noite,
    rendendo 100% da diária — o corte é por duração, não por calendário.
    """

    def test_doze_horas_e_um_minuto_no_mesmo_dia_rendem_diaria_inteira(self):
        """Demonstrativo oficial: R$ 290,55. Sai 08:00, volta 20:01 do mesmo dia."""
        resultado = self.calcular(
            [
                marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 12, 0), ADRIANOPOLIS),
                marcador(datetime(2026, 8, 12, 19, 0), datetime(2026, 8, 12, 20, 1), CURITIBA),
            ],
            datetime(2026, 8, 12, 20, 1),
        )
        self.assertEqual(resultado["totais"]["total_valor_decimal"], Decimal("290.55"))
        trecho = resultado["trechos"][0]
        self.assertEqual(trecho["tipo"], "INTERIOR")
        self.assertEqual(trecho["n_diarias"], 0)
        self.assertEqual(trecho["percentual_adicional"], 100)

    def test_dezesseis_horas_atravessando_a_madrugada(self):
        """Demonstrativo oficial: R$ 371,26, como 0 dias + 16h."""
        resultado = self.calcular(
            [
                marcador(datetime(2026, 8, 12, 20, 0), datetime(2026, 8, 13, 2, 0), SAO_PAULO),
                marcador(datetime(2026, 8, 13, 6, 0), datetime(2026, 8, 13, 12, 0), CURITIBA),
            ],
            datetime(2026, 8, 13, 12, 0),
        )
        self.assertEqual(resultado["totais"]["total_valor_decimal"], Decimal("371.26"))
        trecho = resultado["trechos"][0]
        self.assertEqual(trecho["n_diarias"], 0)
        self.assertEqual(trecho["percentual_adicional"], 100)

    def test_a_escada_completa(self):
        base = datetime(2026, 8, 12, 6, 0)
        casos = {
            5: 0, 6: 0,        # até 6h: nada
            7: 15, 8: 15,      # >6h até 8h
            9: 30, 12: 30,     # >8h até 12h
            13: 100, 20: 100,  # >12h: diária inteira
        }
        for horas, esperado in casos.items():
            with self.subTest(horas=horas):
                _dias, percentual, _r, _t = _decompor(base, base + timedelta(hours=horas))
                self.assertEqual(percentual, esperado)

    def test_cruzar_a_meia_noite_nao_e_criterio(self):
        """Dois minutos entre 23:59 e 00:01 valem zero: é menos de 6 horas."""
        dias, percentual, _r, _t = _decompor(
            datetime(2026, 8, 12, 23, 59), datetime(2026, 8, 13, 0, 1)
        )
        self.assertEqual(dias, 0)
        self.assertEqual(percentual, 0)

    def test_dia_inteiro_mais_resto_longo_soma_duas_diarias(self):
        """44 horas = 1 dia + 20h; o resto passa de 12h e vale outra diária."""
        dias, percentual, _r, _t = _decompor(
            datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 14, 4, 0)
        )
        self.assertEqual(dias, 1)
        self.assertEqual(percentual, 100)


class ReconciliacaoPorServidorTests(BaseDiariasTestCase):
    """O valor por servidor tem de fechar com o total da equipe.

    O ofício traz o total e o relatório traz o valor daquele servidor: se um não
    reconstrói o outro, quem confere não tem como saber qual está certo.
    """

    def cenario(self, nome):
        casos = {
            "misto": (
                [
                    marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO),
                    marcador(datetime(2026, 8, 13, 8, 0), datetime(2026, 8, 13, 18, 0), ABATIA),
                    marcador(datetime(2026, 8, 14, 8, 0), datetime(2026, 8, 14, 18, 0), CURITIBA),
                ],
                datetime(2026, 8, 14, 18, 0),
            ),
            "faixa_unica": (
                [
                    marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO),
                    marcador(datetime(2026, 8, 13, 8, 0), datetime(2026, 8, 13, 14, 0), FLORIANOPOLIS),
                    marcador(datetime(2026, 8, 14, 8, 0), datetime(2026, 8, 14, 16, 0), SAO_PAULO),
                    marcador(datetime(2026, 8, 15, 8, 0), datetime(2026, 8, 15, 16, 0), CURITIBA),
                ],
                datetime(2026, 8, 15, 16, 0),
            ),
            "com_complemento": (
                [
                    marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 12, 0), ABATIA),
                    marcador(datetime(2026, 8, 12, 19, 0), datetime(2026, 8, 12, 20, 1), CURITIBA),
                ],
                datetime(2026, 8, 12, 20, 1),
            ),
        }
        return casos[nome]

    def test_o_valor_por_servidor_reconstroi_o_total(self):
        for nome in ("misto", "faixa_unica", "com_complemento"):
            marcadores, chegada = self.cenario(nome)
            for servidores in (1, 2, 3, 7):
                with self.subTest(roteiro=nome, servidores=servidores):
                    totais = self.calcular(marcadores, chegada, servidores)["totais"]
                    self.assertEqual(
                        totais["valor_por_servidor_decimal"] * servidores,
                        totais["total_valor_decimal"],
                        "o valor por servidor não reconstrói o total",
                    )

    def test_equipe_sem_servidor_nao_divide_por_zero(self):
        marcadores, chegada = self.cenario("misto")
        totais = self.calcular(marcadores, chegada, servidores=0)["totais"]
        self.assertEqual(totais["valor_por_servidor_decimal"], Decimal("0.00"))
        self.assertEqual(totais["total_valor_decimal"], Decimal("0.00"))


class ComposicaoDoTotalTests(BaseDiariasTestCase):
    """A composição explica o total — é o que permite auditar o pagamento."""

    def test_cada_parcela_registra_de_qual_vigencia_saiu(self):
        resultado = self.calcular(
            [
                marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO),
                marcador(datetime(2026, 8, 13, 8, 0), datetime(2026, 8, 13, 18, 0), ABATIA),
                marcador(datetime(2026, 8, 14, 8, 0), datetime(2026, 8, 14, 18, 0), CURITIBA),
            ],
            datetime(2026, 8, 14, 18, 0),
        )
        componentes = resultado.componentes
        # Trecho capital: 1 diária inteira + complemento de 30%. Trecho
        # interior: 1 diária inteira, sem complemento.
        self.assertEqual(
            [(c["faixa"], c["percentual"], c["quantidade"]) for c in componentes],
            [("CAPITAL", 100, 1), ("CAPITAL", 30, 1), ("INTERIOR", 100, 1)],
        )
        for componente in componentes:
            self.assertIsNotNone(componente["tabela_diaria_id"])
            self.assertEqual(componente["tabela_vigencia_inicio"], date(2026, 1, 1))

    def test_a_soma_das_parcelas_e_o_total(self):
        resultado = self.calcular(
            [
                marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO),
                marcador(datetime(2026, 8, 13, 8, 0), datetime(2026, 8, 13, 18, 0), ABATIA),
                marcador(datetime(2026, 8, 14, 8, 0), datetime(2026, 8, 14, 18, 0), CURITIBA),
            ],
            datetime(2026, 8, 14, 18, 0),
            servidores=3,
        )
        soma = sum(c["subtotal"] for c in resultado.componentes)
        self.assertEqual(soma, resultado["totais"]["total_valor_decimal"])


class ClassificacaoDeFaixaTests(TestCase):
    def test_brasilia_tem_faixa_propria(self):
        self.assertEqual(classificar_faixa("Brasília", "DF"), "BRASILIA")

    def test_capital_e_reconhecida_com_e_sem_acento(self):
        self.assertEqual(classificar_faixa("São Paulo", "SP"), "CAPITAL")
        self.assertEqual(classificar_faixa("SAO PAULO", "sp"), "CAPITAL")

    def test_cidade_do_interior_e_interior(self):
        self.assertEqual(classificar_faixa("Abatiá", "PR"), "INTERIOR")

    def test_capital_de_outra_uf_nao_conta(self):
        # "Curitiba" só é capital no Paraná.
        self.assertEqual(classificar_faixa("Curitiba", "SP"), "INTERIOR")

    def test_destino_sem_uf_cai_no_interior(self):
        self.assertEqual(classificar_faixa("Qualquer", ""), "INTERIOR")

    def test_a_tabela_cobre_as_27_unidades_da_federacao(self):
        self.assertEqual(len(CAPITAIS_POR_UF), 27)


class RoteiroSemTabelaTests(TestCase):
    """Sem vigência cadastrada, o cálculo falha de forma visível.

    A origem cai numa tabela fixa no código. Aqui não: valor de diária mora em
    `TabelaDiaria`, e cobrar por um valor que ninguém sabe de onde veio é pior
    que recusar o cálculo.
    """

    def test_sem_vigencia_o_calculo_recusa_em_vez_de_inventar_valor(self):
        with self.assertRaises(SemTabelaDeDiarias):
            calcular_diarias(
                [
                    marcador(
                        datetime(2026, 8, 12, 8, 0),
                        datetime(2026, 8, 12, 18, 0),
                        SAO_PAULO,
                    )
                ],
                datetime(2026, 8, 13, 18, 0),
                sede_cidade="CURITIBA",
                sede_uf="PR",
            )

    def test_a_mensagem_diz_o_que_falta(self):
        TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.INTERIOR,
            vigencia_inicio=date(2026, 1, 1),
            valor_24h=VALOR_INTERIOR,
        )
        with self.assertRaises(SemTabelaDeDiarias) as erro:
            calcular_diarias(
                [marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO)],
                datetime(2026, 8, 13, 18, 0),
                sede_cidade="CURITIBA",
                sede_uf="PR",
            )
        self.assertIn("BRASILIA", str(erro.exception))
        self.assertIn("CAPITAL", str(erro.exception))
        self.assertNotIn("INTERIOR", str(erro.exception))


class RoteiroInvalidoTests(BaseDiariasTestCase):
    def test_roteiro_sem_marcador_nao_calcula(self):
        with self.assertRaises(RoteiroIncalculavel):
            self.calcular([], datetime(2026, 8, 13, 18, 0))

    def test_chegada_final_anterior_a_saida_nao_calcula(self):
        with self.assertRaises(RoteiroIncalculavel):
            self.calcular(
                [marcador(datetime(2026, 8, 12, 8, 0), datetime(2026, 8, 12, 18, 0), SAO_PAULO)],
                datetime(2026, 8, 11, 18, 0),
            )

    def test_vigencia_posterior_a_saida_nao_vale_para_o_roteiro(self):
        # A vigência semeada começa em 01/01/2026; um roteiro de 2025 não tem
        # valor cadastrado e não pode ser calculado por aproximação.
        with self.assertRaises(SemTabelaDeDiarias):
            self.calcular(
                [marcador(datetime(2025, 8, 12, 8, 0), datetime(2025, 8, 12, 18, 0), SAO_PAULO)],
                datetime(2025, 8, 13, 18, 0),
            )
