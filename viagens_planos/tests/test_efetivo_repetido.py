"""O efetivo do plano aceita o mesmo cargo em mais de uma linha."""
from django.test import TestCase

from viagens_cadastros.models import Cargo, Unidade
from viagens_planos.efetivo_services import linhas_do_formset, reconciliar_efetivo
from viagens_planos.forms import EfetivoPlanoFormSet
from viagens_planos.models import PlanoTrabalho


class EfetivoComCargoRepetidoTests(TestCase):
    def setUp(self):
        self.plano = PlanoTrabalho.objects.create()
        self.cargo = Cargo.objects.create(nome="AGENTE DE POLÍCIA")
        self.unidade = Unidade.objects.create(nome="ASCOM")

    def test_formulario_aceita_e_grava_as_duas_linhas(self):
        dados = {
            "efetivo-TOTAL_FORMS": "2", "efetivo-INITIAL_FORMS": "0",
            "efetivo-MIN_NUM_FORMS": "0", "efetivo-MAX_NUM_FORMS": "1000",
            "efetivo-0-unidade": str(self.unidade.pk), "efetivo-0-cargo": str(self.cargo.pk), "efetivo-0-quantidade": "2",
            "efetivo-1-unidade": str(self.unidade.pk), "efetivo-1-cargo": str(self.cargo.pk), "efetivo-1-quantidade": "3",
        }
        formset = EfetivoPlanoFormSet(dados, instance=self.plano, prefix="efetivo")
        self.assertTrue(formset.is_valid(), formset.errors)
        reconciliar_efetivo(self.plano, linhas_do_formset(formset))
        self.assertEqual(sorted(self.plano.efetivos.values_list("quantidade", flat=True)), [2, 3])
        self.assertEqual(self.plano.total_efetivo, 5)
