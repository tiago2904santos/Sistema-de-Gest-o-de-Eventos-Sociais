from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
from io import StringIO
from django.core.management import call_command
from .test_helpers import PrestacaoTestCase as TestCase
from cadastros.models import Municipio as Cidade, Estado, Regiao
from viagens_cadastros.models import Servidor
from viagens_oficios.models import Oficio
from viagens_prestacoes.diario_services import clonar_roteiro
from viagens_prestacoes.models import PrestacaoContas
from viagens_roteiros.models import Roteiro, RoteiroDestino

class MesclarRoteirosAjustadosIdenticosTests(TestCase):

    def setUp(self):
        self.regiao, _ = Regiao.objects.get_or_create(nome='SUL')
        self.estado, _ = Estado.objects.get_or_create(sigla='PR', defaults={'nome': 'PARANA', 'codigo_ibge': '41'})
        self.estado2, _ = Estado.objects.get_or_create(sigla='SC', defaults={'nome': 'SANTA CATARINA', 'codigo_ibge': '42'})
        self.cidade_sede, _ = Cidade.objects.get_or_create(nome='CURITIBA', estado=self.estado, defaults={'regiao': self.regiao, 'codigo_ibge': '4106902'})
        self.cidade_dest, _ = Cidade.objects.get_or_create(nome='FLORIANOPOLIS', estado=self.estado2, defaults={'regiao': self.regiao, 'codigo_ibge': '4205407'})
        self.servidor = Servidor.objects.create(nome='Servidor Teste')

    def _run(self, *args):
        out = StringIO()
        call_command('mesclar_roteiros_ajustados_identicos', *args, stdout=out)
        return out.getvalue()

    def _roteiro_com_destino(self, observacoes=''):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, origem_municipio=self.cidade_sede, observacoes=observacoes)
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.cidade_dest, ordem=0)
        return roteiro

    def test_dry_run_nao_altera_nada(self):
        original = self._roteiro_com_destino()
        oficio = Oficio.objects.create(numero=1, ano=2026, roteiro=original)
        copia = clonar_roteiro(original)
        oficio.servidores.add(self.servidor)
        pc = PrestacaoContas.objects.get(oficio=oficio)
        pc.roteiro_ajustado = copia
        pc.save(update_fields=['roteiro_ajustado'])
        saida = self._run()
        self.assertIn('seriam descartadas', saida)
        pc.refresh_from_db()
        self.assertEqual(pc.roteiro_ajustado_id, copia.pk)
        self.assertTrue(Roteiro.objects.filter(pk=copia.pk).exists())

    def test_confirmar_descarta_copia_identica_e_apaga(self):
        original = self._roteiro_com_destino()
        oficio = Oficio.objects.create(numero=2, ano=2026, roteiro=original)
        copia = clonar_roteiro(original)
        oficio.servidores.add(self.servidor)
        pc = PrestacaoContas.objects.get(oficio=oficio)
        pc.roteiro_ajustado = copia
        pc.save(update_fields=['roteiro_ajustado'])
        saida = self._run('--confirmar')
        self.assertIn('apagada', saida)
        pc.refresh_from_db()
        self.assertIsNone(pc.roteiro_ajustado_id)
        self.assertFalse(Roteiro.objects.filter(pk=copia.pk).exists())
        self.assertTrue(Roteiro.objects.filter(pk=original.pk).exists())

    def test_nao_mexe_em_copia_divergente(self):
        original = self._roteiro_com_destino(observacoes='ORIGINAL')
        oficio = Oficio.objects.create(numero=3, ano=2026, roteiro=original)
        copia = clonar_roteiro(original)
        copia.observacoes = 'AJUSTADO'
        copia.save(update_fields=['observacoes'])
        oficio.servidores.add(self.servidor)
        pc = PrestacaoContas.objects.get(oficio=oficio)
        pc.roteiro_ajustado = copia
        pc.save(update_fields=['roteiro_ajustado'])
        saida = self._run('--confirmar')
        self.assertIn('Nenhuma copia identica', saida)
        pc.refresh_from_db()
        self.assertEqual(pc.roteiro_ajustado_id, copia.pk)
        self.assertTrue(Roteiro.objects.filter(pk=copia.pk).exists())

    def test_nao_apaga_copia_ainda_referenciada_por_outra_prestacao(self):
        original = self._roteiro_com_destino()
        oficio1 = Oficio.objects.create(numero=4, ano=2026, roteiro=original)
        oficio2 = Oficio.objects.create(numero=5, ano=2026)
        copia = clonar_roteiro(original)
        oficio1.servidores.add(self.servidor)
        pc1 = PrestacaoContas.objects.get(oficio=oficio1)
        pc1.roteiro_ajustado = copia
        pc1.save(update_fields=['roteiro_ajustado'])
        servidor2 = Servidor.objects.create(nome='Servidor 2')
        oficio2.servidores.add(servidor2)
        pc2 = PrestacaoContas.objects.get(oficio=oficio2)
        pc2.roteiro_ajustado = copia
        pc2.save(update_fields=['roteiro_ajustado'])
        self._run('--confirmar')
        pc1.refresh_from_db()
        self.assertIsNone(pc1.roteiro_ajustado_id)
        self.assertTrue(Roteiro.objects.filter(pk=copia.pk).exists())
