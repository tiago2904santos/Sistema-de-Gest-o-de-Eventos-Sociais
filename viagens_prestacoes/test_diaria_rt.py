from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
"""`NOVO-20260826-021706-c02af444709b`: a diária do RT era dividida pela equipe.

Teste de caracterização exigido pelo `AGENTS.md` §3.3 (regra de dinheiro): o
contrato do campo é o que está escrito em `Oficio.diarias_para_servidores` —
"o roteiro guarda sempre o valor para 1 servidor" —, e quem grava garante isso
recalculando com `quantidade_servidores=1`
(`roteiros/services/roteiro_editor.py:503`).

O relatório técnico fazia o contrário: dividia esse valor pelo efetivo do
ofício. Com uma diária de R$ 800,00 e equipe de quatro, o ofício autorizava
R$ 3.200,00 (4 × 800) e o RT do mesmo servidor imprimia R$ 200,00.
"""
from decimal import Decimal
from .test_helpers import PrestacaoTestCase as TestCase
from viagens_prestacoes.services import diaria_inicial_da_prestacao, diaria_inicial_do_oficio, valor_diaria_liberado
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin

class DiariaPorServidorNoRelatorioTecnicoTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.servidores = [self.criar_servidor(f'Diarista {indice}') for indice in range(4)]
        self.fixture = self.criar_prestacao(numero=1, servidores=self.servidores)
        self.servidor_prestacao = self.fixture.prestacoes_servidor[0]
        self.prestacao = self.servidor_prestacao.prestacao
        self.oficio = self.prestacao.oficio
        roteiro = self.oficio.roteiro
        roteiro.valor_diarias = Decimal('800.00')
        roteiro.resumo_diarias = '2 x 100%'
        roteiro.save(update_fields=['valor_diarias', 'resumo_diarias'])
        self.oficio.diarias_quantidade_servidores = 4
        self.oficio.save(update_fields=['diarias_quantidade_servidores'])

    def test_oficio_multiplica_o_valor_do_roteiro_pelo_efetivo(self):
        """Lado que já estava certo, congelado aqui: é ele que define o contrato."""
        total = self.oficio.diarias_para_servidores()
        self.assertEqual(total['valor_decimal'], Decimal('3200.00'))
        self.assertEqual(total['quantidade_servidores'], 4)

    def test_rt_imprime_a_diaria_inteira_do_servidor(self):
        self.assertEqual(diaria_inicial_do_oficio(self.prestacao), 'R$800,00')
        self.assertEqual(diaria_inicial_da_prestacao(self.prestacao), 'R$800,00')

    def test_teto_do_que_o_servidor_pode_ter_recebido_e_a_diaria_inteira(self):
        """Com o teto partido pela equipe, digitar o valor impresso era recusado."""
        self.assertEqual(valor_diaria_liberado(self.servidor_prestacao), Decimal('800.00'))

    def test_equipe_maior_nao_encolhe_a_diaria_de_ninguem(self):
        """O tamanho da equipe não altera quanto cada servidor saca."""
        extras = [self.criar_servidor(f'Reforço {i}') for i in range(6)]
        self.oficio.servidores.add(*extras)
        self.assertEqual(diaria_inicial_da_prestacao(self.prestacao), 'R$800,00')
        self.assertEqual(valor_diaria_liberado(self.servidor_prestacao), Decimal('800.00'))

    def test_servidor_sozinho_continua_com_o_mesmo_valor(self):
        """Antes, o caso de 1 servidor era o único que acertava — não pode regredir."""
        solo = self.criar_prestacao(numero=2, servidores=[self.servidores[0]])
        oficio_solo = solo.prestacoes_servidor[0].prestacao.oficio
        roteiro = oficio_solo.roteiro
        roteiro.valor_diarias = Decimal('800.00')
        roteiro.save(update_fields=['valor_diarias'])
        self.assertEqual(valor_diaria_liberado(solo.prestacoes_servidor[0]), Decimal('800.00'))

    def test_sem_roteiro_nao_inventa_valor(self):
        sem_roteiro = self.criar_prestacao(numero=3, com_roteiro=False)
        self.assertEqual(diaria_inicial_da_prestacao(sem_roteiro.prestacoes_servidor[0].prestacao), '')
        self.assertIsNone(valor_diaria_liberado(sem_roteiro.prestacoes_servidor[0]))
