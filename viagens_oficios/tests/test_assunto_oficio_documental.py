import datetime
from django.test import TestCase
from django.utils import timezone
from viagens_cadastros.models import ConfiguracaoSistema
from viagens_oficios.assunto_oficio import ASSUNTO_AUTORIZACAO
from viagens_oficios.assunto_oficio import ASSUNTO_CONVALIDACAO
from viagens_oficios.assunto_oficio import resolver_assunto_oficio
from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context
from viagens_oficios.models import Oficio
from viagens_roteiros.models import Roteiro

class ResolverAssuntoOficioTests(TestCase):

    def setUp(self):
        ConfiguracaoSistema.get_singleton()

    def _roteiro_com_saida(self, dt: datetime.datetime) -> Roteiro:
        r = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        r.saida_dt = timezone.make_aware(dt, timezone.get_current_timezone())
        r.save(update_fields=['saida_dt'])
        return r

    def test_autorizacao_criacao_antes_da_saida(self):
        roteiro = self._roteiro_com_saida(datetime.datetime(2026, 6, 1, 8, 0, 0))
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro)
        r = resolver_assunto_oficio(oficio)
        self.assertEqual(r['assunto_oficio'], '(Autorização)')
        self.assertEqual(r['assunto_termo'], 'autorização')
        self.assertEqual(r['assunto_linha'], ASSUNTO_AUTORIZACAO)

    def test_convalidacao_criacao_apos_ou_igual_saida(self):
        roteiro = self._roteiro_com_saida(datetime.datetime(2026, 5, 10, 8, 0, 0))
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro)
        r = resolver_assunto_oficio(oficio)
        self.assertEqual(r['assunto_oficio'], '(Convalidação)')
        self.assertEqual(r['assunto_termo'], 'convalidação')
        self.assertEqual(r['assunto_linha'], ASSUNTO_CONVALIDACAO)

    def test_retificado_sobre_autorizacao(self):
        roteiro = self._roteiro_com_saida(datetime.datetime(2026, 6, 1, 8, 0, 0))
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro, retificado_documento=True)
        r = resolver_assunto_oficio(oficio)
        self.assertEqual(r['assunto_oficio'], '(Retificado)')
        self.assertEqual(r['assunto_linha'], ASSUNTO_AUTORIZACAO)
        self.assertEqual(r['assunto_termo'], 'autorização')

    def test_complementar_nunca_muda_assunto_termo(self):
        roteiro = self._roteiro_com_saida(datetime.datetime(2026, 6, 1, 8, 0, 0))
        oficio_autorizacao = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro, complementar_documento=True)
        r = resolver_assunto_oficio(oficio_autorizacao)
        self.assertEqual(r['assunto_termo'], 'autorização')
        roteiro2 = self._roteiro_com_saida(datetime.datetime(2026, 5, 1, 8, 0, 0))
        oficio_convalidacao = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro2, complementar_documento=True)
        r2 = resolver_assunto_oficio(oficio_convalidacao)
        self.assertEqual(r2['assunto_termo'], 'convalidação')

    def test_retificado_ignorado_se_ja_convalidacao(self):
        roteiro = self._roteiro_com_saida(datetime.datetime(2026, 5, 1, 8, 0, 0))
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro, retificado_documento=True)
        r = resolver_assunto_oficio(oficio)
        self.assertEqual(r['assunto_oficio'], '(Convalidação)')

class AssuntoLinhaNaoUsaCampoWizardTests(TestCase):

    def setUp(self):
        ConfiguracaoSistema.get_singleton()

    def test_demo_assunto_nao_aparece_no_contexto(self):
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), assunto='[DEMO OFICIO] texto livre')
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertNotIn('[DEMO OFICIO]', ctx['assunto_linha'])
        self.assertEqual(ctx['assunto_linha'], ASSUNTO_AUTORIZACAO)
