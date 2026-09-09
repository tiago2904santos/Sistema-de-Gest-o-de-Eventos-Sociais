"""Fatia 2/6 de T-01 — número de solicitação e datas de liberação.

Primeira fatia que exercita **escrita**: as anteriores só liam. O mesmo campo
(``numero_solicitacao``) tem dois caminhos de gravação:

* ``prestacao_servidor_solicitacao_autosave`` — o caminho com JS;
* ``index`` com ``action=save_solicitacoes`` — o *fallback* sem JS.

O ``NOVO-103`` exige o mesmo contrato nos dois: validar toda a requisição antes de
gravar, informar data inválida e marcar o servidor em preenchimento.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
import json
from datetime import date
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes.models import PrestacaoServidor
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin

class SolicitacaoAutosaveTests(PrestacaoFixturesMixin, TestCase):
    """O caminho com JS: POST JSON no endpoint de autosave."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.ps = self.fixture.prestacoes_servidor[0]

    def autosave(self, ps=None, **campos):
        ps = ps or self.ps
        payload = {'model': 'prestacao_servidor', 'object_id': str(ps.pk), 'dirty_fields': list(campos), 'fields': campos}
        return self.client.post(reverse('viagens_prestacoes:prestacao_servidor_solicitacao_autosave', args=[ps.pk]), data=json.dumps(payload), content_type='application/json')

    def test_autosave_persiste_numero_e_devolve_identidade(self):
        response = self.autosave(numero_solicitacao='  2026 / 0001  ')
        corpo = response.json()
        self.assertTrue(corpo['ok'])
        self.assertEqual(corpo['object_id'], self.ps.pk)
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, '2026 / 0001')

    def test_autosave_avanca_status_de_pendente_para_em_preenchimento(self):
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_PENDENTE)
        self.autosave(numero_solicitacao='A-1')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO)

    def test_autosave_nao_rebaixa_status_ja_avancado(self):
        """``marcar_em_preenchimento`` só age em PENDENTE — salvar não regride."""
        PrestacaoServidor.objects.filter(pk=self.ps.pk).update(status=PrestacaoServidor.STATUS_APROVADA)
        self.autosave(numero_solicitacao='A-2')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_APROVADA)
        self.assertEqual(self.ps.numero_solicitacao, 'A-2')

    def test_autosave_grava_datas_em_formato_iso(self):
        self.autosave(data_liberacao_diarias='2026-08-10', prazo_limite_saque='2026-08-20')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.data_liberacao_diarias, date(2026, 8, 10))
        self.assertEqual(self.ps.prazo_limite_saque, date(2026, 8, 20))

    def test_autosave_recusa_data_invalida_com_mensagem_e_nao_persiste(self):
        self.autosave(data_liberacao_diarias='2026-08-10')
        response = self.autosave(data_liberacao_diarias='10/08/2026')
        corpo = response.json()
        self.assertFalse(corpo['ok'])
        self.assertEqual(corpo['message'], 'Data de liberação inválida.')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.data_liberacao_diarias, date(2026, 8, 10))

    def test_autosave_recusa_prazo_invalido_com_mensagem_propria(self):
        response = self.autosave(prazo_limite_saque='ontem')
        corpo = response.json()
        self.assertFalse(corpo['ok'])
        self.assertEqual(corpo['message'], 'Data de prazo limite inválida.')

    def test_autosave_recusa_payload_de_outro_modelo(self):
        response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_solicitacao_autosave', args=[self.ps.pk]), data=json.dumps({'model': 'roteiro', 'fields': {'numero_solicitacao': 'X'}}), content_type='application/json')
        self.assertFalse(response.json()['ok'])
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, '')

class SolicitacaoEmLoteTests(PrestacaoFixturesMixin, TestCase):
    """O caminho sem JS: POST no index com ``action=save_solicitacoes``."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.ps = self.fixture.prestacoes_servidor[0]

    def salvar_em_lote(self, **campos):
        dados = {'action': 'save_solicitacoes'}
        for nome, valor in campos.items():
            dados[f'ps-{self.ps.pk}-{nome}'] = valor
        return self.client.post(reverse('viagens_prestacoes:index'), dados)

    def test_lote_persiste_numero_normalizado_de_varios_servidores(self):
        segunda = self.criar_prestacao(numero=2)
        ps2 = segunda.prestacoes_servidor[0]
        self.client.post(reverse('viagens_prestacoes:index'), {'action': 'save_solicitacoes', f'ps-{self.ps.pk}-numero_solicitacao': '  A   1  ', f'ps-{ps2.pk}-numero_solicitacao': 'B-2'})
        self.ps.refresh_from_db()
        ps2.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, 'A 1')
        self.assertEqual(ps2.numero_solicitacao, 'B-2')

    def test_lote_grava_datas_e_prazo(self):
        self.salvar_em_lote(data_liberacao_diarias='2026-09-01', prazo_limite_saque='2026-09-15')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.data_liberacao_diarias, date(2026, 9, 1))
        self.assertEqual(self.ps.prazo_limite_saque, date(2026, 9, 15))

    def test_lote_avisa_data_invalida_e_nao_grava_outro_campo(self):
        """A requisição sem JS é atômica também para erro de validação (NOVO-103)."""
        self.salvar_em_lote(data_liberacao_diarias='2026-09-01')
        response = self.salvar_em_lote(numero_solicitacao='NAO-DEVE-ENTRAR', data_liberacao_diarias='01/09/2026')
        self.assertEqual(response.status_code, 302)
        mensagens = [str(message) for message in response.wsgi_request._messages]
        self.assertEqual(mensagens[-1], 'Data de liberação inválida.')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, '')
        self.assertEqual(self.ps.data_liberacao_diarias, date(2026, 9, 1))

    def test_lote_marca_em_preenchimento(self):
        """O status não depende de o navegador executar JavaScript (NOVO-103)."""
        self.salvar_em_lote(numero_solicitacao='SEM-JS-1')
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, 'SEM-JS-1')
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO)

    def test_lote_sem_campos_reconhecidos_nao_altera_nada(self):
        self.salvar_em_lote(numero_solicitacao='ORIGINAL')
        self.ps.refresh_from_db()
        atualizado_em = self.ps.atualizado_em
        self.client.post(reverse('viagens_prestacoes:index'), {'action': 'save_solicitacoes', 'campo-desconhecido': 'x'})
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, 'ORIGINAL')
        self.assertEqual(self.ps.atualizado_em, atualizado_em)
