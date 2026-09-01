"""Modelos de roteiro e a gravação do cálculo de diárias.

A régua do cálculo em si está em ``tests_caracterizacao.py``; aqui se prova que
o banco defende as regras por conta própria e que o resultado do motor chega
íntegro às tabelas.
"""

from datetime import date, datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from cadastros.models import Estado, Municipio, Regiao
from viagens_cadastros.models import TabelaDiaria

from .models import Roteiro, RoteiroDestino, RoteiroDiariaComponente, RoteiroTrecho
from .services.calculo import chegada_final, marcadores_do_roteiro, recalcular_diarias
from .services.diarias import RoteiroIncalculavel


def dt(ano, mes, dia, hora, minuto=0):
    """Data e hora no fuso do sistema — é o que a produção grava."""
    return timezone.make_aware(datetime(ano, mes, dia, hora, minuto))


class BaseRoteiroTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Estados e regiões já vêm semeados por migração.
        cls.pr, _ = Estado.objects.get_or_create(
            sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41}
        )
        cls.sp, _ = Estado.objects.get_or_create(
            sigla="SP", defaults={"nome": "São Paulo", "codigo_ibge": 35}
        )
        cls.capital, _ = Regiao.objects.get_or_create(nome="Capital")
        cls.interior, _ = Regiao.objects.get_or_create(nome="Interior")
        cls.curitiba, _ = Municipio.objects.get_or_create(
            nome="Curitiba", estado=cls.pr, defaults={"regiao": cls.capital}
        )
        cls.abatia, _ = Municipio.objects.get_or_create(
            nome="Abatiá", estado=cls.pr, defaults={"regiao": cls.interior}
        )
        cls.sao_paulo, _ = Municipio.objects.get_or_create(
            nome="São Paulo", estado=cls.sp, defaults={"regiao": cls.capital}
        )
        for faixa, valor in (
            (TabelaDiaria.Faixa.INTERIOR, Decimal("290.55")),
            (TabelaDiaria.Faixa.CAPITAL, Decimal("371.26")),
            (TabelaDiaria.Faixa.BRASILIA, Decimal("468.12")),
        ):
            TabelaDiaria.objects.create(
                faixa=faixa, vigencia_inicio=date(2026, 1, 1), valor_24h=valor
            )

    def roteiro_curitiba_sp_abatia(self):
        """O roteiro do demonstrativo oficial de R$ 773,19, montado no banco."""
        roteiro = Roteiro.objects.create(
            origem_municipio=self.curitiba,
            saida_dt=dt(2026, 8, 12, 8, 0),
            retorno_chegada_dt=dt(2026, 8, 14, 18, 0),
            quantidade_servidores=1,
        )
        RoteiroTrecho.objects.create(
            roteiro=roteiro,
            ordem=1,
            origem_municipio=self.curitiba,
            destino_municipio=self.sao_paulo,
            saida_dt=dt(2026, 8, 12, 8, 0),
            chegada_dt=dt(2026, 8, 12, 18, 0),
        )
        RoteiroTrecho.objects.create(
            roteiro=roteiro,
            ordem=2,
            origem_municipio=self.sao_paulo,
            destino_municipio=self.abatia,
            saida_dt=dt(2026, 8, 13, 8, 0),
            chegada_dt=dt(2026, 8, 13, 18, 0),
        )
        RoteiroTrecho.objects.create(
            roteiro=roteiro,
            ordem=3,
            origem_municipio=self.abatia,
            destino_municipio=self.curitiba,
            saida_dt=dt(2026, 8, 14, 8, 0),
            chegada_dt=dt(2026, 8, 14, 18, 0),
        )
        return roteiro


class ConstraintsDoRoteiroTests(BaseRoteiroTestCase):
    def test_banco_recusa_volta_anterior_a_saida(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Roteiro.objects.create(
                    saida_dt=dt(2026, 8, 14, 8, 0),
                    retorno_chegada_dt=dt(2026, 8, 12, 8, 0),
                )

    def test_banco_aceita_ida_e_volta_no_mesmo_instante(self):
        # Degenerado, não impossível: o que se barra é a inversão.
        instante = dt(2026, 8, 12, 8, 0)
        roteiro = Roteiro.objects.create(saida_dt=instante, retorno_chegada_dt=instante)
        self.assertIsNotNone(roteiro.pk)

    def test_banco_aceita_roteiro_com_datas_em_branco(self):
        # Rascunho começa vazio; a constraint só se aplica quando há as duas datas.
        self.assertIsNotNone(Roteiro.objects.create().pk)

    def test_banco_recusa_valor_de_diarias_negativo(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Roteiro.objects.create(valor_diarias=Decimal("-1.00"))

    def test_destino_nao_repete_ordem_no_mesmo_roteiro(self):
        roteiro = Roteiro.objects.create()
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.abatia, ordem=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RoteiroDestino.objects.create(
                    roteiro=roteiro, municipio=self.sao_paulo, ordem=1
                )

    def test_trecho_nao_aceita_chegada_antes_da_saida(self):
        roteiro = Roteiro.objects.create()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RoteiroTrecho.objects.create(
                    roteiro=roteiro,
                    ordem=1,
                    saida_dt=dt(2026, 8, 12, 18, 0),
                    chegada_dt=dt(2026, 8, 12, 8, 0),
                )

    def test_trecho_nao_aceita_distancia_negativa(self):
        roteiro = Roteiro.objects.create()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RoteiroTrecho.objects.create(
                    roteiro=roteiro, ordem=1, distancia_km=Decimal("-5.00")
                )

    def test_parcela_de_diaria_exige_quantidade_positiva(self):
        roteiro = Roteiro.objects.create()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RoteiroDiariaComponente.objects.create(
                    roteiro=roteiro,
                    ordem=1,
                    faixa="INTERIOR",
                    percentual=100,
                    quantidade=0,
                    valor_unitario=Decimal("290.55"),
                    subtotal=Decimal("0.00"),
                )


class CancelamentoTests(BaseRoteiroTestCase):
    def test_cancelar_guarda_o_motivo_e_a_data(self):
        roteiro = Roteiro.objects.create()
        roteiro.cancelar("Evento adiado")
        roteiro.refresh_from_db()
        self.assertTrue(roteiro.cancelado)
        self.assertEqual(roteiro.motivo_cancelamento, "Evento adiado")
        self.assertIsNotNone(roteiro.cancelado_em)

    def test_reativar_limpa_o_cancelamento(self):
        roteiro = Roteiro.objects.create()
        roteiro.cancelar("Engano")
        roteiro.reativar()
        roteiro.refresh_from_db()
        self.assertFalse(roteiro.cancelado)
        self.assertEqual(roteiro.motivo_cancelamento, "")
        self.assertIsNone(roteiro.cancelado_em)


class MarcadoresTests(BaseRoteiroTestCase):
    def test_cada_trecho_de_ida_vira_um_marcador_na_ordem(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        marcadores = marcadores_do_roteiro(roteiro)
        self.assertEqual(
            [(m.destino_cidade, m.destino_uf) for m in marcadores],
            [("São Paulo", "SP"), ("Abatiá", "PR"), ("Curitiba", "PR")],
        )

    def test_trecho_de_retorno_nao_vira_marcador(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        roteiro.trechos.filter(ordem=3).update(sentido=RoteiroTrecho.Sentido.RETORNO)
        self.assertEqual(len(marcadores_do_roteiro(roteiro)), 2)

    def test_trecho_sem_destino_e_ignorado(self):
        roteiro = Roteiro.objects.create()
        RoteiroTrecho.objects.create(
            roteiro=roteiro, ordem=1, saida_dt=dt(2026, 8, 12, 8, 0)
        )
        self.assertEqual(marcadores_do_roteiro(roteiro), [])

    def test_sem_retorno_a_chegada_final_e_a_do_ultimo_trecho(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        Roteiro.objects.filter(pk=roteiro.pk).update(retorno_chegada_dt=None)
        roteiro.refresh_from_db()
        self.assertEqual(chegada_final(roteiro), dt(2026, 8, 14, 18, 0))


class GravacaoDoCalculoTests(BaseRoteiroTestCase):
    def test_o_roteiro_do_demonstrativo_grava_o_valor_oficial(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        roteiro.refresh_from_db()
        self.assertEqual(roteiro.valor_diarias, Decimal("773.19"))
        self.assertEqual(roteiro.resumo_diarias, "2 x 100% + 1 x 30%")
        self.assertIn("setecentos", roteiro.valor_diarias_extenso)

    def test_a_composicao_gravada_soma_o_total(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        parcelas = roteiro.componentes_diarias.all()
        self.assertEqual(parcelas.count(), 3)
        self.assertEqual(
            sum(p.subtotal for p in parcelas), Decimal("773.19")
        )
        self.assertEqual([p.ordem for p in parcelas], [1, 2, 3])

    def test_cada_parcela_aponta_a_vigencia_que_a_sustentou(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        for parcela in roteiro.componentes_diarias.all():
            self.assertIsNotNone(parcela.tabela_diaria_id)
            self.assertEqual(parcela.tabela_vigencia_inicio, date(2026, 1, 1))

    def test_recalcular_substitui_as_parcelas_em_vez_de_acumular(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        primeiras = list(roteiro.componentes_diarias.values_list("pk", flat=True))
        recalcular_diarias(roteiro)
        segundas = list(roteiro.componentes_diarias.values_list("pk", flat=True))
        self.assertEqual(len(segundas), 3)
        self.assertFalse(set(primeiras) & set(segundas))

    def test_equipe_maior_multiplica_o_total(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        roteiro.quantidade_servidores = 3
        roteiro.save(update_fields=["quantidade_servidores"])
        recalcular_diarias(roteiro)
        roteiro.refresh_from_db()
        self.assertEqual(roteiro.valor_diarias, Decimal("773.19") * 3)

    def test_o_horario_exibido_e_o_local_e_nao_o_do_banco(self):
        """Datas vêm do banco em UTC; exibi-las cruas adiantaria 3 horas.

        O operador digitou 08:00 e é 08:00 que tem de sair no documento — não
        as 11:00 em que o instante está gravado.
        """
        roteiro = self.roteiro_curitiba_sp_abatia()
        roteiro.refresh_from_db()
        resultado = recalcular_diarias(roteiro)
        primeiro = resultado["trechos"][0]
        self.assertEqual(primeiro["data_saida"], "12/08/2026")
        self.assertEqual(primeiro["hora_saida"], "08:00")

    def test_roteiro_sem_trecho_recusa_o_calculo(self):
        roteiro = Roteiro.objects.create(origem_municipio=self.curitiba)
        with self.assertRaises(RoteiroIncalculavel):
            recalcular_diarias(roteiro)

    def test_a_vigencia_protege_as_parcelas_ja_gravadas(self):
        # Apagar uma vigência usada apagaria a explicação de um pagamento.
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        tabela = roteiro.componentes_diarias.first().tabela_diaria
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            tabela.delete()
