from unittest.mock import MagicMock, patch

from django.apps import apps
from django.core.management.base import CommandError
from django.db import IntegrityError, models, transaction
from django.test import SimpleTestCase, TestCase

from migracao_legado.origem import OrigemSQL, RouterLegado, abrir_origem


class OrigemSQLTests(SimpleTestCase):
    def test_identificadores_nao_permitem_injecao(self):
        for valor in ['auth_user; DROP TABLE x', 'x"', '../x', 'x.y', '']:
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                OrigemSQL.identificador(valor)

    def test_tokens_sao_excluidos_antes_da_consulta(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [[('id',), ('link_token',), ('link_token_hash',), ('status',)], [(7, 'assinada')]]
        self.assertEqual(OrigemSQL(cursor).linhas('prestacoes_contas_assinaturadocumento'), [{'id': 7, 'status': 'assinada'}])
        consulta = cursor.execute.call_args.args[0]
        self.assertNotIn('link_token', consulta)
        self.assertTrue(consulta.startswith('SELECT '))

    def test_lista_explicita_tambem_nao_le_tokens(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(7,)]
        self.assertEqual(OrigemSQL(cursor).linhas('assinatura', colunas=['id', 'link_token']), [{'id': 7}])
        self.assertNotIn('link_token', cursor.execute.call_args.args[0])

    def test_snapshot_exige_confirmacao_de_somente_leitura(self):
        from contextlib import nullcontext
        conn = MagicMock(vendor='postgresql')
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ('off',)
        with patch('migracao_legado.origem.connections', {'legado': conn}), patch('migracao_legado.origem.transaction.atomic', return_value=nullcontext()):
            with self.assertRaisesMessage(CommandError, 'somente leitura'):
                with abrir_origem():
                    self.fail('Não deveria liberar a leitura.')
        self.assertIn('READ ONLY', cursor.execute.call_args_list[0].args[0])

    def test_origem_ausente_tem_erro_util_sem_tentar_conectar(self):
        with patch('migracao_legado.origem.connections', {}), self.assertRaisesMessage(CommandError, 'LEGADO_DB_NAME'):
            with abrir_origem():
                self.fail('Não deveria abrir a origem.')

    def test_router_nunca_migra_legado(self):
        router = RouterLegado()
        self.assertFalse(router.allow_migrate('legado', 'accounts'))
        self.assertIsNone(router.allow_migrate('default', 'accounts'))

    def test_tabela_inexistente_nao_parece_origem_vazia(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        with self.assertRaisesMessage(CommandError, 'Tabela de origem ausente'):
            OrigemSQL(cursor).linhas('auth_user')


class OrigemSchemaTests(TestCase):
    def test_metadados_nao_aparecem_no_formulario_institucional(self):
        from viagens_oficios.catalogs import ConfiguracaoInstitucionalForm
        self.assertNotIn('legado_pk', ConfiguracaoInstitucionalForm.base_fields)
        self.assertNotIn('legado_origem', ConfiguracaoInstitucionalForm.base_fields)

    def test_entidades_de_viagens_possuem_marca_e_unicidade(self):
        labels = ['viagens_cadastros', 'viagens_roteiros', 'viagens_oficios', 'viagens_termos', 'viagens_prestacoes', 'documentos']
        for label in labels:
            for model in apps.get_app_config(label).get_models():
                with self.subTest(model=model._meta.label):
                    self.assertTrue(model._meta.get_field('legado_pk').null)
                    self.assertTrue(any(isinstance(c, models.UniqueConstraint) and tuple(c.fields) == ('legado_origem', 'legado_pk') and c.condition is not None for c in model._meta.constraints))

    def test_chave_repetida_recusada_mas_nativos_permitidos(self):
        model = apps.get_model('viagens_cadastros.Unidade')
        model.objects.create(nome='NATIVA A')
        model.objects.create(nome='NATIVA B')
        model.objects.create(nome='IMPORTADA A', legado_origem='gerenciador_viagens', legado_pk=17)
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.create(nome='IMPORTADA B', legado_origem='gerenciador_viagens', legado_pk=17)

    def test_documentos_preservam_uuid_de_origem(self):
        import uuid
        model = apps.get_model('documentos.DocumentoArtefato')
        origem_pk = uuid.uuid4()
        obj = model.objects.create(tipo='oficio', formato='pdf', legado_origem='gerenciador_viagens', legado_pk=origem_pk)
        obj.refresh_from_db()
        self.assertEqual(obj.legado_pk, origem_pk)

    def test_clone_de_roteiro_importado_e_nativo_inclusive_filhos(self):
        from viagens_prestacoes.diario_services import clonar_roteiro
        from viagens_roteiros.models import Roteiro, RoteiroTrecho, RoteiroDiariaComponente
        marca = {'legado_origem': 'gerenciador_viagens', 'legado_pk': 17}
        origem = Roteiro.objects.create(**marca)
        RoteiroTrecho.objects.create(roteiro=origem, **marca)
        RoteiroDiariaComponente.objects.create(roteiro=origem, faixa='INTERIOR', percentual=100, valor_unitario=100, subtotal=100, **marca)
        copia = clonar_roteiro(origem)
        for obj in [copia, copia.trechos.get(), copia.componentes_diarias.get()]:
            self.assertIsNone(obj.legado_pk)
            self.assertEqual(obj.legado_origem, '')
        origem.refresh_from_db()
        self.assertEqual(origem.legado_pk, 17)

    def test_saida_da_equipe_preserva_linha_importada_sem_valores(self):
        from viagens_oficios.models import Oficio
        from viagens_cadastros.models import Servidor
        from viagens_prestacoes.models import PrestacaoServidor
        oficio = Oficio.objects.create()
        servidor = Servidor.objects.create(nome='SERVIDOR DA ORIGEM')
        obj = PrestacaoServidor.objects.create(prestacao=oficio.prestacao_contas, servidor=servidor, legado_origem='gerenciador_viagens', legado_pk=91)
        self.assertTrue(obj.sair_da_equipe())
        obj.refresh_from_db()
        self.assertIsNotNone(obj.removida_em)
        self.assertEqual(obj.legado_pk, 91)

    def test_historico_preserva_data_da_rota_e_parcela_sem_valor(self):
        from django.utils import timezone
        from viagens_roteiros.models import Roteiro, RoteiroTrecho, RoteiroDiariaComponente
        roteiro = Roteiro.objects.create()
        instante = timezone.now()
        trecho = RoteiroTrecho.objects.create(roteiro=roteiro, rota_calculada_em=instante)
        parcela = RoteiroDiariaComponente.objects.create(roteiro=roteiro, origem='LEGADO', faixa='INTERIOR', percentual=100, quantidade=5, valor_unitario=None, subtotal=None)
        trecho.refresh_from_db()
        parcela.refresh_from_db()
        self.assertEqual(trecho.rota_calculada_em, instante)
        self.assertIsNone(parcela.valor_unitario)
        self.assertIsNone(parcela.subtotal)
