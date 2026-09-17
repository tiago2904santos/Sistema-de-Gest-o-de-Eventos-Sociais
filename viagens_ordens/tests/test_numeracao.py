"""A numeração da OS: a menor lacuna liberada por exclusão, senão o maior número mais um."""

from unittest import mock

from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from core.deletion import DelecaoProtegidaError
from viagens_ordens.models import OrdemServico, OrdemServicoNumeroLacuna
from viagens_ordens.services import excluir_ordem_servico


class NumeracaoTests(TestCase):
    def setUp(self):
        self.ano = timezone.localdate().year

    def criar(self, **campos):
        hoje = timezone.localdate()
        return OrdemServico.objects.create(data_evento_inicio=hoje, data_evento_fim=hoje, **campos)

    def test_a_primeira_os_do_ano_recebe_o_numero_1(self):
        ordem = self.criar()
        self.assertEqual((ordem.numero, ordem.ano), (1, self.ano))
        self.assertEqual(ordem.numero_formatado, f"OS 001/{self.ano}")

    def test_a_numeracao_segue_o_maior_usado_mais_um(self):
        self.criar()
        self.criar()
        self.assertEqual(self.criar().numero, 3)

    def test_numero_liberado_por_exclusao_e_reaproveitado(self):
        self.criar()
        excluida = self.criar()
        self.criar()
        excluir_ordem_servico(excluida)
        self.assertTrue(OrdemServicoNumeroLacuna.objects.filter(ano=self.ano, numero=2).exists())
        self.assertEqual(self.criar().numero, 2)
        self.assertFalse(OrdemServicoNumeroLacuna.objects.filter(ano=self.ano, numero=2).exists())

    def test_numero_apenas_pulado_manualmente_nao_vira_lacuna(self):
        self.criar()
        self.criar(numero=5, ano=self.ano)
        self.assertEqual(self.criar().numero, 6)
        self.assertFalse(OrdemServicoNumeroLacuna.objects.exists())

    def test_falha_ao_registrar_lacuna_desfaz_a_exclusao(self):
        ordem = self.criar()
        # `delete()` zera o pk da instância mesmo com a transação desfeita.
        pk = ordem.pk
        with mock.patch.object(OrdemServicoNumeroLacuna.objects, "get_or_create", side_effect=RuntimeError("falha ao registrar lacuna")):
            with self.assertRaisesRegex(RuntimeError, "falha ao registrar lacuna"):
                excluir_ordem_servico(ordem)
        self.assertTrue(OrdemServico.objects.filter(pk=pk).exists())

    def test_exclusao_protegida_nao_cria_lacuna(self):
        ordem = self.criar()
        with mock.patch.object(ordem, "delete", side_effect=ProtectedError("vinculada", {ordem})):
            with self.assertRaises(DelecaoProtegidaError):
                excluir_ordem_servico(ordem)
        self.assertTrue(OrdemServico.objects.filter(pk=ordem.pk).exists())
        self.assertFalse(OrdemServicoNumeroLacuna.objects.exists())

    def test_numero_ja_definido_e_respeitado(self):
        self.assertEqual(self.criar(numero=42, ano=self.ano).numero, 42)

    def test_editar_nao_renumera(self):
        ordem = self.criar()
        ordem.motivo = "outro"
        ordem.save()
        self.assertEqual(ordem.numero, 1)
        self.assertEqual(OrdemServico.objects.count(), 1)
