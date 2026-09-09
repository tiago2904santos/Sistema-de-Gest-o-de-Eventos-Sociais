from decimal import Decimal
from django.test import TestCase
from viagens_cadastros.models import Cargo
from viagens_cadastros.models import ConfiguracaoSistema
from viagens_cadastros.models import Servidor
from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context
from viagens_oficios.models import Oficio
from viagens_roteiros.models import Roteiro

class DiariasDocxtplTests(TestCase):

    def setUp(self):
        ConfiguracaoSistema.get_singleton()

    def test_valor_com_milhar_e_centavos(self):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        roteiro.resumo_diarias = '10'
        roteiro.valor_diarias = Decimal('1500.5')
        roteiro.save(update_fields=['resumo_diarias', 'valor_diarias'])
        oficio = Oficio.objects.create(roteiro=roteiro)
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertTrue(ctx['diaria'].startswith('R$1.500,50'))
        self.assertEqual(ctx['valor_total_oficio'], ctx['diaria'])

    def test_valor_com_extenso(self):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        roteiro.resumo_diarias = '1'
        roteiro.valor_diarias = Decimal('100')
        roteiro.valor_diarias_extenso = 'CEM REAIS'
        roteiro.save(update_fields=['resumo_diarias', 'valor_diarias', 'valor_diarias_extenso'])
        oficio = Oficio.objects.create(roteiro=roteiro)
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertIn('R$100,00', ctx['diaria'])
        self.assertIn('(Cem reais)', ctx['diaria'])

    def test_valor_multiplica_pelo_numero_de_servidores(self):
        """O roteiro guarda o valor de 1 servidor; o documento multiplica pelo efetivo do ofício."""
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO)
        roteiro.resumo_diarias = '1 x 100%'
        roteiro.valor_diarias = Decimal('100')
        roteiro.valor_diarias_extenso = 'CEM REAIS'
        roteiro.save(update_fields=['resumo_diarias', 'valor_diarias', 'valor_diarias_extenso'])
        oficio = Oficio.objects.create(roteiro=roteiro)
        cargo = Cargo.objects.create(nome='Cargo Diaria')
        oficio.servidores.add(Servidor.objects.create(nome='Servidor A', cargo=cargo, cpf='11122233344'), Servidor.objects.create(nome='Servidor B', cargo=cargo, cpf='55566677788'), Servidor.objects.create(nome='Servidor C', cargo=cargo, cpf='99988877766'))
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertIn('R$300,00', ctx['diaria'])
        self.assertIn('(Trezentos reais)', ctx['diaria'])

    def test_excluir_servidor_preserva_total_impresso(self):
        """NOVO-39: uma exclusão cadastral não reescreve dinheiro histórico."""
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, status=Roteiro.Status.RASCUNHO, resumo_diarias='1 x 100%', valor_diarias=Decimal('100'), valor_diarias_extenso='CEM REAIS')
        oficio = Oficio.objects.create(roteiro=roteiro)
        cargo = Cargo.objects.create(nome='Cargo NOVO-39')
        primeiro = Servidor.objects.create(nome='Servidor mantido', cargo=cargo, cpf='12345678901')
        excluido = Servidor.objects.create(nome='Servidor excluído', cargo=cargo, cpf='10987654321')
        oficio.servidores.add(primeiro, excluido)
        oficio.diarias_quantidade_servidores = 2
        oficio.save(update_fields=['diarias_quantidade_servidores'])
        antes = oficio.diarias_para_servidores()
        excluido.delete()
        depois = oficio.diarias_para_servidores()
        self.assertEqual(antes['quantidade_servidores'], 2)
        self.assertEqual(antes['valor_decimal'], Decimal('200'))
        self.assertEqual(depois['quantidade_servidores'], 2)
        self.assertEqual(depois['valor_decimal'], Decimal('200'))
