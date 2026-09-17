"""As diárias com o motor da casa, reproduzindo os planos reais 20/2026 (Maringá) e 18/2026 (Sarandi)."""

from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from viagens_planos.models import EfetivoPlano, PlanoTrabalho
from viagens_planos.services import (
    adicionar_evento_ao_plano,
    atualizar_snapshot_diarias,
    calcular_diarias_combinadas,
    calcular_diarias_plano,
    montar_valor_do_plano_texto,
)

from .fixtures import CenarioPlanoMixin


class DiariasPlanoTests(CenarioPlanoMixin, TestCase):
    def test_maringa_4x100_mais_1x15(self):
        resultado = calcular_diarias_plano(self.criar_plano_maringa(efetivo=6))
        self.assertTrue(resultado["ok"], resultado.get("erros"))
        self.assertEqual(resultado["composicao"], "4 x 100% + 1 x 15%")
        self.assertEqual(resultado["valor_unitario"], Decimal("1205.78"))
        self.assertEqual(resultado["valor_total"], Decimal("7234.68"))
        self.assertEqual(resultado["valor_unitario_display"], "1.205,78")
        self.assertEqual(resultado["valor_total_display"], "7.234,68")

    def test_sarandi_5x100_mais_1x30(self):
        plano = PlanoTrabalho.objects.create(
            destino_estado=self.uf, destino_cidade=self.sarandi,
            saida_sede_data=date(2026, 6, 23), saida_sede_hora=time(7, 0),
            chegada_sede_data=date(2026, 6, 28), chegada_sede_hora=time(16, 0),
        )
        EfetivoPlano.objects.create(plano=plano, cargo=self.cargo_policial, quantidade=18)
        resultado = calcular_diarias_plano(plano)
        self.assertTrue(resultado["ok"], resultado.get("erros"))
        self.assertEqual(resultado["composicao"], "5 x 100% + 1 x 30%")
        self.assertEqual(resultado["valor_unitario"], Decimal("1539.92"))
        self.assertEqual(resultado["valor_total"], Decimal("27718.56"))

    def test_snapshot_e_texto_do_valor(self):
        plano = self.criar_plano_maringa()
        atualizar_snapshot_diarias(plano)
        plano.refresh_from_db()
        self.assertEqual(plano.diarias_composicao, "4 x 100% + 1 x 15%")
        self.assertEqual(plano.diarias_valor_total, Decimal("7234.68"))
        texto = montar_valor_do_plano_texto(plano)
        self.assertIn("Valor total: R$7.234,68", texto)
        self.assertIn("4 x 100% + 1 x 15%", texto)
        self.assertIn("R$1.205,78", texto)
        self.assertIn("sete mil", texto.lower())

    def test_calculo_ao_vivo_com_outro_efetivo(self):
        resultado = calcular_diarias_plano(self.criar_plano_maringa(), total_efetivo=10)
        self.assertEqual(resultado["valor_total"], Decimal("12057.80"))

    def test_dados_incompletos_e_chegada_antes_da_saida(self):
        self.assertFalse(calcular_diarias_plano(PlanoTrabalho.objects.create())["ok"])
        plano = self.criar_plano_maringa()
        plano.chegada_sede_data = plano.saida_sede_data
        plano.chegada_sede_hora = time(6, 0)
        self.assertEqual(calcular_diarias_plano(plano)["erros"], ["A chegada na sede deve ser depois da saída."])

    def test_sem_tabela_vigente_o_calculo_recusa(self):
        from viagens_cadastros.models import TabelaDiaria

        TabelaDiaria.objects.all().delete()
        resultado = calcular_diarias_plano(self.criar_plano_maringa())
        self.assertFalse(resultado["ok"])
        self.assertIn("Não há valor de diária vigente", resultado["erros"][0])


class DiariasMultiEventoTests(CenarioPlanoMixin, TestCase):
    def test_evento_gravado_e_combinado(self):
        plano = self.criar_plano_maringa()
        evento = adicionar_evento_ao_plano(plano)
        plano.refresh_from_db()
        self.assertTrue(plano.is_multi_evento)
        self.assertEqual(evento.diarias_composicao, "")  # o evento nasce sem snapshot próprio
        self.assertEqual(plano.diarias_combinada_composicao, "4 x 100% + 1 x 15%")
        self.assertEqual(plano.diarias_combinada_valor_total, Decimal("7234.68"))
        self.assertIsNone(plano.destino_cidade)  # o rascunho foi limpo
        self.assertEqual(calcular_diarias_combinadas(plano)["quantidade_servidores"], 6)
