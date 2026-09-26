from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
"""Caracterização da listagem e entrada de prestações de contas (T-01)."""
from datetime import timedelta
from .test_helpers import PrestacaoTestCase as TestCase
from django.utils import timezone
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin

class PrestacaoListagemAtualTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        self.setUpPrestacaoFixtures()

    @staticmethod
    def _card_pks(response):
        return [card['ps_pk'] for card in response.context['cards']]

    def test_sem_situacao_escolhida_a_lista_abre_inteira(self):
        """Sem `?aba=`, nenhum recorte (2026-08-21).

        A tela abria na aba `nao_liberadas` — uma fila de trabalho legítima, mas
        que escondia liberadas, arquivadas e finalizadas sem dizer que havia
        filtro ligado. É o mesmo contrato das demais listas do sistema.
        """
        ativa = self.criar_prestacao(numero=1)
        liberada = self.criar_prestacao(numero=2, data_liberacao_diarias=timezone.localdate())
        arquivada = self.criar_prestacao(numero=3, arquivada=True)
        finalizada = self.criar_prestacao(numero=4, finalizada=True)
        response = self.get_listagem()
        self.assertEqual(response.context['abas_selecionadas'], [])
        self.assertFalse(response.context['has_filters'])
        self.assertEqual(set(self._card_pks(response)), {fixture.prestacoes_servidor[0].pk for fixture in (ativa, liberada, arquivada, finalizada)})
        self.assertEqual(response.context['page_obj'].paginator.count, 4)

    def test_situacao_escolhida_recorta_a_lista(self):
        ativa = self.criar_prestacao(numero=1)
        self.criar_prestacao(numero=2, data_liberacao_diarias=timezone.localdate())
        response = self.get_listagem(aba='nao_liberadas')
        self.assertEqual(response.context['abas_selecionadas'], ['nao_liberadas'])
        self.assertTrue(response.context['has_filters'])
        self.assertEqual(self._card_pks(response), [ativa.prestacoes_servidor[0].pk])
        self.assertEqual(response.context['cards'][0]['status_value'], 'pendente')

    def test_card_expoe_identidade_e_status_atuais_da_prestacao(self):
        servidor = self.criar_servidor('Carla Investigadora')
        fixture = self.criar_prestacao(numero=7, servidor=servidor, status='em_preenchimento')
        response = self.get_listagem()
        card = response.context['cards'][0]
        self.assertEqual(card['prestacao_pk'], fixture.prestacao.pk)
        self.assertEqual(card['numero_display'], fixture.oficio.numero_formatado)
        self.assertEqual(card['status_value'], 'em_preenchimento')
        self.assertEqual(card['servidores'][0]['name'], 'CARLA INVESTIGADORA')

    def test_listagem_nao_exibe_prestacao_de_oficio_cancelado(self):
        visivel = self.criar_prestacao(numero=1)
        cancelada = self.criar_prestacao(numero=2, cancelado=True)
        response = self.get_listagem()
        self.assertTrue(cancelada.oficio.cancelado)
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertEqual(self._card_pks(response), [visivel.prestacoes_servidor[0].pk])
        self.assertNotIn(cancelada.prestacoes_servidor[0].pk, self._card_pks(response))

    def test_dois_servidores_da_mesma_prestacao_formam_grupo_consecutivo(self):
        servidores = (self.criar_servidor('Servidor Inicial'), self.criar_servidor('Servidor Final'))
        fixture = self.criar_prestacao(numero=30, servidores=servidores)
        response = self.get_listagem()
        cards = response.context['cards']
        self.assertEqual([card['ps_pk'] for card in cards], [ps.pk for ps in fixture.prestacoes_servidor])
        self.assertEqual([card['equipe_count'] for card in cards], [2, 2])
        # Os dois servidores do mesmo ofício viram uma linha só, e a página conta ofícios.
        grupos = response.context['grupos']
        self.assertEqual([[c['ps_pk'] for c in g['cards']] for g in grupos], [[ps.pk for ps in fixture.prestacoes_servidor]])
        self.assertEqual(response.context['page_obj'].paginator.count, 1)

    def test_ordenacao_padrao_usa_criacao_desc_e_desempata_por_prestacao_e_pk(self):
        agora = timezone.now()
        antiga_a = self.criar_prestacao(numero=10, criado_em=agora - timedelta(days=2))
        antiga_b = self.criar_prestacao(numero=20, criado_em=agora - timedelta(days=2))
        recente = self.criar_prestacao(numero=30, criado_em=agora - timedelta(days=1))
        response = self.get_listagem()
        self.assertEqual(self._card_pks(response), [recente.prestacoes_servidor[0].pk, antiga_a.prestacoes_servidor[0].pk, antiga_b.prestacoes_servidor[0].pk])

    def test_abas_sao_mutuamente_exclusivas_e_mostram_contagens_exatas(self):
        nao_liberada = self.criar_prestacao(numero=1)
        liberada = self.criar_prestacao(numero=2, data_liberacao_diarias=timezone.localdate())
        arquivada = self.criar_prestacao(numero=3, arquivada=True)
        finalizada = self.criar_prestacao(numero=4, finalizada=True)
        casos = {'nao_liberadas': nao_liberada.prestacoes_servidor[0].pk, 'liberadas': liberada.prestacoes_servidor[0].pk, 'arquivados': arquivada.prestacoes_servidor[0].pk, 'finalizados': finalizada.prestacoes_servidor[0].pk}
        for aba, ps_pk in casos.items():
            with self.subTest(aba=aba):
                response = self.get_listagem(aba=aba)
                self.assertEqual(self._card_pks(response), [ps_pk])
                self.assertEqual({item['value']: item['label'] for item in response.context['situacao_options']}, {'nao_liberadas': 'Não liberadas (1)', 'liberadas': 'Liberadas (1)', 'arquivados': 'Arquivados (1)', 'finalizados': 'Finalizados (1)', 'saque_vencendo': 'Saque vencendo (0)', 'prestacao_vencida': 'Prestação vencida (0)'})

    def test_filtro_status_retem_somente_status_de_dominio_solicitado(self):
        aprovada = self.criar_prestacao(numero=1, status='aprovada')
        pendente = self.criar_prestacao(numero=2, status='pendente')
        response = self.get_listagem(status='aprovada')
        self.assertEqual(self._card_pks(response), [aprovada.prestacoes_servidor[0].pk])
        self.assertEqual(response.context['cards'][0]['status_value'], 'aprovada')
        self.assertNotIn(pendente.prestacoes_servidor[0].pk, self._card_pks(response))

    def test_primeira_pagina_tem_vinte_cards_e_preserva_total_real(self):
        fixtures = [self.criar_prestacao(numero=numero) for numero in range(1, 22)]
        response = self.get_listagem()
        self.assertEqual(len(response.context['cards']), 20)
        self.assertEqual(response.context['page_obj'].paginator.count, 21)
        self.assertEqual({card['status_value'] for card in response.context['cards']}, {'pendente'})
        self.assertNotIn(fixtures[0].prestacoes_servidor[0].pk, self._card_pks(response))

    def test_cada_aba_vazia_expoe_sua_mensagem_de_dominio(self):
        mensagens = {'nao_liberadas': 'Nenhum servidor com diárias pendentes de liberação.', 'liberadas': 'Nenhum servidor com diárias já liberadas.', 'arquivados': 'Nenhuma prestação de servidor arquivada.', 'finalizados': 'Nenhuma prestação de servidor finalizada ainda.'}
        for aba, mensagem in mensagens.items():
            with self.subTest(aba=aba):
                response = self.get_listagem(aba=aba)
                self.assertEqual(response.context['cards'], [])
                self.assertEqual(response.context['empty_message'], mensagem)
                self.assertContains(response, mensagem)

    def test_busca_encontra_nome_acentuado_e_ano_numerico_do_oficio(self):
        acentuada = self.criar_prestacao(numero=11, servidor=self.criar_servidor('Álvaro Pêra'))
        ano = self.criar_prestacao(numero=12, ano=2042)
        ignorada = self.criar_prestacao(numero=13, ano=2026)
        por_nome = self.get_listagem(q='Alvaro Pera')
        por_ano = self.get_listagem(q='2042')
        self.assertEqual(self._card_pks(por_nome), [acentuada.prestacoes_servidor[0].pk])
        self.assertEqual(self._card_pks(por_ano), [ano.prestacoes_servidor[0].pk])
        self.assertNotIn(ignorada.prestacoes_servidor[0].pk, self._card_pks(por_ano))

    def test_sort_oficio_asc_ordena_por_ano_numero_prestacao_e_pk(self):
        oficio_30 = self.criar_prestacao(numero=30)
        oficio_5 = self.criar_prestacao(numero=5)
        oficio_17 = self.criar_prestacao(numero=17)
        response = self.get_listagem(sort='oficio_asc')
        self.assertEqual(self._card_pks(response), [oficio_5.prestacoes_servidor[0].pk, oficio_17.prestacoes_servidor[0].pk, oficio_30.prestacoes_servidor[0].pk])
