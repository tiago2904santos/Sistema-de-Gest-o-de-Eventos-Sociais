import datetime
from django.test import TestCase
from django.utils import timezone
from viagens_cadastros.models import ConfiguracaoSistema
from viagens_oficios.justificativas_services import avaliar_justificativa_oficio
from viagens_oficios.justificativas_services import calcular_dias_antecedencia_justificativa
from viagens_oficios.justificativas_services import get_prazo_justificativa_dias
from viagens_oficios.justificativas_services import get_primeira_saida_oficio
from viagens_oficios.justificativas_services import oficio_exige_justificativa
from viagens_oficios.models import Oficio
from viagens_roteiros.models import Roteiro
from viagens_roteiros.models import RoteiroTrecho

class JustificativaPrazoServicesTests(TestCase):

    def setUp(self):
        ConfiguracaoSistema.get_singleton()

    def test_get_prazo_retorna_configuracao(self):
        cfg = ConfiguracaoSistema.get_singleton()
        cfg.prazo_justificativa_dias = 10
        cfg.save(update_fields=['prazo_justificativa_dias'])
        self.assertEqual(get_prazo_justificativa_dias(), 10)

    def test_saida_em_10_dias_exige(self):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        roteiro.saida_dt = timezone.make_aware(datetime.datetime(2026, 5, 20, 8, 0, 0), timezone.get_current_timezone())
        roteiro.save(update_fields=['saida_dt'])
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro)
        self.assertTrue(oficio_exige_justificativa(oficio))
        ev = avaliar_justificativa_oficio(oficio)
        self.assertEqual(ev['status'], 'required')
        self.assertEqual(ev['dias_antecedencia'], 10)

    def test_saida_em_11_dias_nao_exige(self):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        roteiro.saida_dt = timezone.make_aware(datetime.datetime(2026, 5, 21, 8, 0, 0), timezone.get_current_timezone())
        roteiro.save(update_fields=['saida_dt'])
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro)
        self.assertFalse(oficio_exige_justificativa(oficio))
        ev = avaliar_justificativa_oficio(oficio)
        self.assertEqual(ev['status'], 'not_applicable')
        self.assertEqual(ev['dias_antecedencia'], 11)

    def test_saida_mesmo_dia_exige(self):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        roteiro.saida_dt = timezone.make_aware(datetime.datetime(2026, 5, 10, 14, 0, 0), timezone.get_current_timezone())
        roteiro.save(update_fields=['saida_dt'])
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro)
        self.assertTrue(oficio_exige_justificativa(oficio))

    def test_saida_antes_da_criacao_exige(self):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        roteiro.saida_dt = timezone.make_aware(datetime.datetime(2026, 5, 9, 8, 0, 0), timezone.get_current_timezone())
        roteiro.save(update_fields=['saida_dt'])
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro)
        self.assertTrue(oficio_exige_justificativa(oficio))
        ev = avaliar_justificativa_oficio(oficio)
        self.assertLess(ev['dias_antecedencia'], 0)

    def test_sem_roteiro_unknown(self):
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10))
        ev = avaliar_justificativa_oficio(oficio)
        self.assertEqual(ev['status'], 'unknown')
        self.assertFalse(ev['obrigatoria'])

    def test_roteiro_sem_data_saida_unknown(self):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro)
        ev = avaliar_justificativa_oficio(oficio)
        self.assertEqual(ev['status'], 'unknown')

    def test_primeira_saida_vem_do_primeiro_trecho_com_saida(self):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        RoteiroTrecho.objects.create(roteiro=roteiro, ordem=0, sentido=RoteiroTrecho.Sentido.IDA, saida_dt=timezone.make_aware(datetime.datetime(2026, 6, 1, 8, 0, 0), timezone.get_current_timezone()))
        RoteiroTrecho.objects.create(roteiro=roteiro, ordem=1, sentido=RoteiroTrecho.Sentido.IDA, saida_dt=timezone.make_aware(datetime.datetime(2026, 6, 15, 8, 0, 0), timezone.get_current_timezone()))
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro)
        ps = get_primeira_saida_oficio(oficio)
        self.assertIsNotNone(ps)
        self.assertEqual(ps.astimezone(timezone.get_current_timezone()).date(), datetime.date(2026, 6, 1))
        self.assertEqual(calcular_dias_antecedencia_justificativa(oficio), (datetime.date(2026, 6, 1) - datetime.date(2026, 5, 10)).days)

    def test_timezone_aware_naive_normalizado(self):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        roteiro.saida_dt = datetime.datetime(2026, 5, 20, 8, 0, 0)
        self.assertTrue(timezone.is_naive(roteiro.saida_dt))
        roteiro.save(update_fields=['saida_dt'])
        oficio = Oficio.objects.create(data_criacao=datetime.date(2026, 5, 10), roteiro=roteiro)
        ps = get_primeira_saida_oficio(oficio)
        self.assertTrue(timezone.is_aware(ps))
        self.assertTrue(oficio_exige_justificativa(oficio))
