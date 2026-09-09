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

class DiagnosticarRoteirosAjustadosTests(TestCase):

    def setUp(self):
        self.regiao, _ = Regiao.objects.get_or_create(nome='SUL')
        self.estado, _ = Estado.objects.get_or_create(sigla='PR', defaults={'nome': 'PARANA', 'codigo_ibge': '41'})
        self.estado2, _ = Estado.objects.get_or_create(sigla='SC', defaults={'nome': 'SANTA CATARINA', 'codigo_ibge': '42'})
        self.cidade_sede, _ = Cidade.objects.get_or_create(nome='CURITIBA', estado=self.estado, defaults={'regiao': self.regiao, 'codigo_ibge': '4106902'})
        self.cidade_dest, _ = Cidade.objects.get_or_create(nome='FLORIANOPOLIS', estado=self.estado2, defaults={'regiao': self.regiao, 'codigo_ibge': '4205407'})
        self.servidor = Servidor.objects.create(nome='Servidor Teste')

    def _run(self):
        out = StringIO()
        call_command('diagnosticar_roteiros_ajustados', stdout=out)
        return out.getvalue()

    def _roteiro_com_destino(self, observacoes=''):
        roteiro = Roteiro.objects.create(tipo=Roteiro.Tipo.AVULSO, origem_municipio=self.cidade_sede, observacoes=observacoes)
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.cidade_dest, ordem=0)
        return roteiro

    def test_copia_identica_e_marcada_como_segura(self):
        original = self._roteiro_com_destino()
        oficio = Oficio.objects.create(numero=1, ano=2026, roteiro=original)
        copia = clonar_roteiro(original)
        oficio.servidores.add(self.servidor)
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        prestacao.roteiro_ajustado = copia
        prestacao.save(update_fields=['roteiro_ajustado'])
        saida = self._run()
        self.assertIn('IDENTICA', saida)
        self.assertIn('1 identicas', saida)
        self.assertIn('0 divergentes', saida)

    def test_copia_alterada_e_marcada_como_divergente(self):
        original = self._roteiro_com_destino(observacoes='ORIGINAL')
        oficio = Oficio.objects.create(numero=2, ano=2026, roteiro=original)
        copia = clonar_roteiro(original)
        copia.observacoes = 'AJUSTADO'
        copia.save(update_fields=['observacoes'])
        oficio.servidores.add(self.servidor)
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        prestacao.roteiro_ajustado = copia
        prestacao.save(update_fields=['roteiro_ajustado'])
        saida = self._run()
        self.assertIn('DIVERGENTE', saida)
        self.assertIn('observacoes', saida)
        self.assertIn('0 identicas', saida)
        self.assertIn('1 divergentes', saida)
