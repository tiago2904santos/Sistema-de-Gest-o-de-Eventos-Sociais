"""Rede transacional de `BE-14` e contrato unificado por `NOVO-103`.

As duas rotas implementam a mesma regra (número da solicitação, data de liberação e
prazo limite). A rede prova atomicidade diante de falha de banco e de validação, tanto
dentro de um autosave quanto entre servidores do lote.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
import json
from datetime import date
from unittest import mock
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes.models import PrestacaoServidor
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin

class SolicitacaoAutosaveParcialTests(PrestacaoFixturesMixin, TestCase):
    """O autosave grava campo a campo, e o erro chega depois da primeira gravação."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=51)
        self.ps = self.fixture.prestacoes_servidor[0]

    def autosave(self, **campos):
        payload = {'model': 'prestacao_servidor', 'object_id': str(self.ps.pk), 'dirty_fields': list(campos), 'fields': campos}
        return self.client.post(reverse('viagens_prestacoes:prestacao_servidor_solicitacao_autosave', args=[self.ps.pk]), data=json.dumps(payload), content_type='application/json')

    def test_data_invalida_impede_gravacao_parcial_do_numero(self):
        """O autosave valida todos os campos antes da primeira escrita (NOVO-103)."""
        resposta = self.autosave(numero_solicitacao='SOL-2026-1', data_liberacao_diarias='01/09/2026')
        corpo = json.loads(resposta.content)
        self.assertFalse(corpo['ok'])
        self.assertEqual(corpo['message'], 'Data de liberação inválida.')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, '')
        self.assertIsNone(self.ps.data_liberacao_diarias)

    def test_prazo_invalido_impede_gravacao_parcial_dos_campos_anteriores(self):
        """Erro no terceiro campo rejeita a requisição inteira (NOVO-103)."""
        resposta = self.autosave(numero_solicitacao='SOL-2026-2', data_liberacao_diarias='2026-09-01', prazo_limite_saque='15/09/2026')
        corpo = json.loads(resposta.content)
        self.assertFalse(corpo['ok'])
        self.assertEqual(corpo['message'], 'Data de prazo limite inválida.')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, '')
        self.assertIsNone(self.ps.data_liberacao_diarias)
        self.assertIsNone(self.ps.prazo_limite_saque)

    def test_tudo_valido_grava_os_tres_campos_e_marca_o_servidor(self):
        resposta = self.autosave(numero_solicitacao='SOL-2026-3', data_liberacao_diarias='2026-09-01', prazo_limite_saque='2026-09-15')
        self.assertTrue(json.loads(resposta.content)['ok'])
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, 'SOL-2026-3')
        self.assertEqual(self.ps.data_liberacao_diarias, date(2026, 9, 1))
        self.assertEqual(self.ps.prazo_limite_saque, date(2026, 9, 15))
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO)

    def test_campo_ausente_do_payload_nao_e_apagado(self):
        """`None` significa "não veio", e não "limpar" — o autosave manda só o sujo."""
        self.autosave(data_liberacao_diarias='2026-09-01')
        self.autosave(numero_solicitacao='SOL-2026-4')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, 'SOL-2026-4')
        self.assertEqual(self.ps.data_liberacao_diarias, date(2026, 9, 1), 'a segunda requisição não mandou a data, e ela não podia sumir')

class SolicitacaoEmLoteTransacaoTests(PrestacaoFixturesMixin, TestCase):
    """O caminho sem JS: um `UPDATE` por servidor, num laço, sem transação."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.primeiro = self.criar_servidor('Primeiro SOL')
        self.segundo = self.criar_servidor('Segundo SOL')
        self.fixture = self.criar_prestacao(numero=52, servidores=[self.primeiro, self.segundo])
        self.ps_a, self.ps_b = self.fixture.prestacoes_servidor

    def salvar_em_lote(self, **por_servidor):
        dados = {'action': 'save_solicitacoes'}
        for ps, campos in por_servidor.items():
            for nome, valor in campos.items():
                dados[f'ps-{ps}-{nome}'] = valor
        return self.client.post(reverse('viagens_prestacoes:index'), dados)

    def test_lote_grava_os_dois_servidores(self):
        self.salvar_em_lote(**{str(self.ps_a.pk): {'numero_solicitacao': 'LOTE-A'}, str(self.ps_b.pk): {'numero_solicitacao': 'LOTE-B'}})
        self.ps_a.refresh_from_db()
        self.ps_b.refresh_from_db()
        self.assertEqual(self.ps_a.numero_solicitacao, 'LOTE-A')
        self.assertEqual(self.ps_b.numero_solicitacao, 'LOTE-B')

    def test_data_invalida_em_um_servidor_rejeita_o_lote_inteiro(self):
        self.salvar_em_lote(**{str(self.ps_a.pk): {'numero_solicitacao': 'NAO-ENTRA-A'}, str(self.ps_b.pk): {'numero_solicitacao': 'NAO-ENTRA-B', 'data_liberacao_diarias': '01/09/2026'}})
        self.ps_a.refresh_from_db()
        self.ps_b.refresh_from_db()
        self.assertEqual(self.ps_a.numero_solicitacao, '')
        self.assertEqual(self.ps_b.numero_solicitacao, '')
        self.assertIsNone(self.ps_b.data_liberacao_diarias)

    def test_falha_no_meio_do_laco_nao_deixa_meia_gravacao(self):
        """Era o defeito do `BE-14` no lote, e é a razão de o service ser atômico.

        Reprovava no commit da rede e passou a valer quando o laço saiu da view para
        `solicitacao_services.salvar_solicitacoes_em_lote`.
        """
        original = PrestacaoServidor.save
        chamadas = []

        def falhar_na_segunda(self_ps, *args, **kwargs):
            chamadas.append(self_ps.pk)
            if len(chamadas) == 2:
                raise RuntimeError('falha no meio do lote de solicitações')
            return original(self_ps, *args, **kwargs)
        with mock.patch.object(PrestacaoServidor, 'save', falhar_na_segunda):
            with self.assertRaises(RuntimeError):
                self.salvar_em_lote(**{str(self.ps_a.pk): {'numero_solicitacao': 'LOTE-A'}, str(self.ps_b.pk): {'numero_solicitacao': 'LOTE-B'}})
        self.ps_a.refresh_from_db()
        self.ps_b.refresh_from_db()
        self.assertEqual(self.ps_a.numero_solicitacao, '')
        self.assertEqual(self.ps_b.numero_solicitacao, '')
