"""Fatia 5/6 de T-01 — arquivamento e finalização.

São as transições que tiram a prestação da mesa. Duas características do
desenho atual ficam registradas aqui, sem juízo de valor:

* os endpoints são **alternadores**, não atribuições — o mesmo POST arquiva e
  desarquiva. Um duplo envio desfaz a ação;
* **não há pré-condição**: finalizar não exige comprovante, relatório técnico
  nem número de solicitação. A decisão é inteiramente do operador.

A segunda pode ser deliberada — é uma pergunta de produto, não um defeito
óbvio. Está travada como está para que uma mudança futura seja uma escolha
explícita, e não um efeito colateral.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes.models import PrestacaoServidor
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin

class ArquivamentoTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.ps = self.fixture.prestacoes_servidor[0]

    def arquivar(self, ps=None):
        ps = ps or self.ps
        return self.client.post(reverse('viagens_prestacoes:prestacao_servidor_arquivar', args=[ps.pk]))

    def test_arquivar_marca_flag_e_carimba_o_momento(self):
        self.assertFalse(self.ps.arquivada)
        self.assertIsNone(self.ps.arquivada_em)
        self.arquivar()
        self.ps.refresh_from_db()
        self.assertTrue(self.ps.arquivada)
        self.assertIsNotNone(self.ps.arquivada_em)

    def test_segundo_post_desarquiva_e_limpa_o_carimbo(self):
        """O endpoint alterna. Duplo envio desfaz — não é idempotente."""
        self.arquivar()
        self.arquivar()
        self.ps.refresh_from_db()
        self.assertFalse(self.ps.arquivada)
        self.assertIsNone(self.ps.arquivada_em)

    def test_arquivar_move_o_card_para_a_situacao_de_arquivados(self):
        """O recorte é comparado entre SITUAÇÕES, e não contra a lista sem filtro.

        Antes, o teste conferia que o card sumia da lista sem `?aba=` — o que
        valia enquanto a tela abria na aba `nao_liberadas`. Desde 2026-08-21 a
        lista abre INTEIRA, e "some da lista inteira" seria justamente o
        contrário do desejado: arquivar não some com o registro, muda a
        situação dele.
        """
        self.arquivar()
        pendentes = [c['ps_pk'] for c in self.get_listagem(aba='nao_liberadas').context['cards']]
        arquivados = [c['ps_pk'] for c in self.get_listagem(aba='arquivados').context['cards']]
        inteira = [c['ps_pk'] for c in self.get_listagem().context['cards']]
        self.assertNotIn(self.ps.pk, pendentes)
        self.assertEqual(arquivados, [self.ps.pk])
        self.assertIn(self.ps.pk, inteira)

    def test_get_nao_arquiva(self):
        """A ação é destrutiva o bastante para exigir POST."""
        response = self.client.get(reverse('viagens_prestacoes:prestacao_servidor_arquivar', args=[self.ps.pk]))
        self.assertEqual(response.status_code, 405)
        self.ps.refresh_from_db()
        self.assertFalse(self.ps.arquivada)

class FinalizacaoTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.ps = self.fixture.prestacoes_servidor[0]

    def finalizar(self, ps=None):
        ps = ps or self.ps
        return self.client.post(reverse('viagens_prestacoes:prestacao_servidor_finalizar', args=[ps.pk]))

    def test_finalizar_marca_flag_e_carimba_o_momento(self):
        self.finalizar()
        self.ps.refresh_from_db()
        self.assertTrue(self.ps.finalizada)
        self.assertIsNotNone(self.ps.finalizada_em)

    def test_segundo_post_reabre_e_limpa_o_carimbo(self):
        """Também alterna: finalizar não é irreversível nem idempotente."""
        self.finalizar()
        self.finalizar()
        self.ps.refresh_from_db()
        self.assertFalse(self.ps.finalizada)
        self.assertIsNone(self.ps.finalizada_em)

    def test_finalizar_nao_exige_nenhuma_pre_condicao(self):
        """Sem comprovante, sem RT e sem número de solicitação, finaliza igual.

        Caracterização, não aprovação: pode ser decisão de produto (o operador
        é quem julga). Fica travado para que mudar isso seja escolha explícita.
        """
        self.assertEqual(self.ps.numero_solicitacao, '')
        self.assertEqual(self.ps.documentos_anexos.count(), 0)
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_PENDENTE)
        self.finalizar()
        self.ps.refresh_from_db()
        self.assertTrue(self.ps.finalizada)
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_PENDENTE)

    def test_finalizar_move_o_card_para_a_situacao_de_finalizados(self):
        """Comparado entre SITUAÇÕES — ver a nota do teste de arquivamento."""
        self.finalizar()
        pendentes = [c['ps_pk'] for c in self.get_listagem(aba='nao_liberadas').context['cards']]
        finalizados = [c['ps_pk'] for c in self.get_listagem(aba='finalizados').context['cards']]
        inteira = [c['ps_pk'] for c in self.get_listagem().context['cards']]
        self.assertNotIn(self.ps.pk, pendentes)
        self.assertEqual(finalizados, [self.ps.pk])
        self.assertIn(self.ps.pk, inteira)

class AcoesPorOficioTests(PrestacaoFixturesMixin, TestCase):
    """As rotas antigas, por ofício, mantidas por compatibilidade."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()

    def test_finalizar_por_oficio_atinge_apenas_o_primeiro_servidor(self):
        """Contrato declarado na view: delega ao primeiro servidor, só a ele.

        Num ofício com equipe, a rota antiga finaliza um e deixa os outros —
        por isso a tela usa as rotas por servidor.
        """
        segundo = self.criar_servidor('Servidor Dois')
        fixture = self.criar_prestacao(numero=1, servidores=[self.criar_servidor('Servidor Um'), segundo])
        ps_um, ps_dois = sorted(fixture.prestacoes_servidor, key=lambda ps: ps.pk)
        self.client.post(reverse('viagens_prestacoes:prestacao_finalizar', args=[fixture.prestacao.pk]))
        ps_um.refresh_from_db()
        ps_dois.refresh_from_db()
        self.assertTrue(ps_um.finalizada)
        self.assertFalse(ps_dois.finalizada)
