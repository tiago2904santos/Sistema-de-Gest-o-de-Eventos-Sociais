from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import Mock, patch
from types import SimpleNamespace

from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, SimpleTestCase

from core.numeracao import bloquear_escopo_numeracao, colisao_de_numero, NAMESPACE_OFICIO
from viagens_oficios.models import Oficio, OficioNumeroLacuna, ConfiguracaoNumeracaoOficio
from viagens_oficios.services import reservar_numero_oficio, excluir_oficio


class NumeracaoTests(TestCase):
    def reservar(self, ano=2026):
        return reservar_numero_oficio(Oficio(), ano=ano)

    def test_lacuna_do_meio_reutilizada(self):
        a, b, c = [self.reservar() for _ in range(3)]
        excluir_oficio(b)
        self.assertEqual(self.reservar().numero, 2)
        self.assertFalse(OficioNumeroLacuna.objects.exists())
        self.assertEqual(self.reservar().numero, 4)

    def test_menor_lacuna_primeiro(self):
        itens = [self.reservar() for _ in range(5)]
        excluir_oficio(itens[3])
        excluir_oficio(itens[1])
        self.assertEqual([self.reservar().numero for _ in range(2)], [2, 4])

    def test_salto_manual_nao_vira_lacuna(self):
        Oficio.objects.create(ano=2026, numero=15)
        self.assertEqual(self.reservar().numero, 16)

    def test_piso_e_ano(self):
        ConfiguracaoNumeracaoOficio.objects.create(ano=2026, numero_inicial=20)
        OficioNumeroLacuna.objects.create(ano=2026, numero=2)
        self.assertEqual(self.reservar().numero, 20)
        self.assertEqual(self.reservar(2027).numero, 1)

    def test_reserva_idempotente(self):
        o = self.reservar()
        reservar_numero_oficio(o)
        self.assertEqual(o.numero, 1)
        self.assertEqual(Oficio.objects.count(), 1)

    def test_constraint_real(self):
        self.reservar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Oficio.objects.create(numero=1, ano=2026)

    def test_retry_colisao_real(self):
        self.reservar()
        with patch('viagens_oficios.services.get_next_available_numero_oficio', side_effect=[1, 2]):
            self.assertEqual(self.reservar().numero, 2)

    def test_fallback_select_for_update(self):
        self.reservar()
        original = Oficio.objects.select_for_update
        with patch('core.numeracao.connection.vendor', 'sqlite'), patch.object(Oficio.objects, 'select_for_update', wraps=original) as lock:
            self.assertEqual(self.reservar().numero, 2)
        lock.assert_called_once()

    def test_rollback_nao_consume_numero(self):
        try:
            with transaction.atomic():
                self.reservar()
                raise ValueError('rollback')
        except ValueError:
            pass
        self.assertEqual(self.reservar().numero, 1)


class DiagnosticoTests(SimpleTestCase):
    def test_metadado_tem_precedencia(self):
        exc = IntegrityError()
        exc.__cause__ = Exception()
        exc.__cause__.diag = SimpleNamespace(constraint_name='numero')
        ocupado = Mock(return_value=False)
        self.assertTrue(colisao_de_numero(exc, constraint='numero', ja_ocupado=ocupado, numero=1))
        ocupado.assert_not_called()

    def test_outra_constraint_nao_e_colisao(self):
        exc = IntegrityError()
        exc.__cause__ = Exception()
        exc.__cause__.diag = SimpleNamespace(constraint_name='outra')
        self.assertFalse(colisao_de_numero(exc, constraint='numero', ja_ocupado=lambda n: True, numero=1))


class ConcorrenciaTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Os testes históricos da F1 voltam o grafo até seu próprio destino.
        # Restabelece os apps desta fase antes de abrir conexões concorrentes.
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    @skipUnless(connection.vendor == 'postgresql', 'Concorrência por advisory lock é específica do PostgreSQL.')
    def test_duas_reservas_simultaneas(self):
        barreira = Barrier(2)

        def reservar():
            try:
                barreira.wait(timeout=10)
                return reservar_numero_oficio(Oficio(), ano=2026).numero
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            numeros = list(pool.map(lambda _: reservar(), range(2)))
        self.assertEqual(sorted(numeros), [1, 2])
        self.assertEqual(Oficio.objects.count(), 2)
