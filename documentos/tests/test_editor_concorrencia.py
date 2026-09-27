"""Duas pessoas no mesmo documento (m125): conflito só no mesmo campo, quem
mexeu na mensagem, presença de quem está editando e versão da linha do diário.
"""
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from documentos.editor.concorrencia import conflito, marcar_presenca, registrar_mudanca
from viagens_oficios.tests.fixtures import CenarioOficioMixin


class ConflitoPorCampoTests(CenarioOficioMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.oficio = self.criar()
        self.colega = get_user_model().objects.create_user(username='colega', first_name='Fulana', last_name='Silva', deve_trocar_senha=False)
        self.colega.setores.add(self.setor)
        self.colega.groups.set(self.user.groups.all())

    def url(self, chave):
        return reverse('documentos:editor_campo', args=['oficio', self.oficio.pk, chave])

    def patch(self, chave, valores, versao):
        return self.client.patch(self.url(chave), data=json.dumps({'valores': valores, 'versao': versao}), content_type='application/json')

    def test_outra_pessoa_em_outro_campo_nao_trava_a_gravacao(self):
        self.oficio.refresh_from_db()
        lida = self.oficio.atualizado_em.isoformat()
        # A colega grava o protocolo depois que eu abri o documento.
        self.client.force_login(self.colega)
        self.assertEqual(self.patch('protocolo', {'protocolo': '987654321'}, lida).status_code, 200)
        # Eu gravo o motivo com a versão que li: passa, e responde a versão nova.
        self.client.force_login(self.user)
        r = self.patch('motivo', {'motivo': 'Reunião em Londrina'}, lida)
        self.assertEqual(r.status_code, 200, r.content)
        self.oficio.refresh_from_db()
        self.assertEqual(self.oficio.motivo, 'Reunião em Londrina')
        self.assertEqual(self.oficio.protocolo, '987654321')
        self.assertEqual(r.json()['versao'], self.oficio.atualizado_em.isoformat())

    def test_o_mesmo_campo_mudado_e_conflito_e_diz_quem_mexeu(self):
        self.oficio.refresh_from_db()
        lida = self.oficio.atualizado_em.isoformat()
        self.client.force_login(self.colega)
        self.assertEqual(self.patch('motivo', {'motivo': 'Motivo da colega'}, lida).status_code, 200)
        self.client.force_login(self.user)
        r = self.patch('motivo', {'motivo': 'Meu motivo'}, lida)
        self.assertEqual(r.status_code, 409)
        self.assertIn('Fulana Silva', r.json()['mensagem'])
        self.assertIn('Motivo', r.json()['mensagem'])
        self.oficio.refresh_from_db()
        self.assertEqual(self.oficio.motivo, 'Motivo da colega')

    def test_sem_a_memoria_das_mudancas_a_versao_antiga_continua_conflito(self):
        r = self.patch('motivo', {'motivo': 'Outro'}, '2020-01-01T00:00:00')
        self.assertEqual(r.status_code, 409)
        self.assertTrue(r.json()['conflito'])

    def test_cadeia_de_mudancas(self):
        registrar_mudanca(self.oficio, 'v1', 'v2', ['protocolo'], self.colega)
        registrar_mudanca(self.oficio, 'v2', 'v3', ['custeio'], self.colega)
        self.assertIsNone(conflito(self.oficio, 'v1', 'v3', ['motivo']))
        self.assertEqual(conflito(self.oficio, 'v1', 'v3', ['custeio'])['quem'], 'Fulana Silva')
        # Cadeia quebrada (mudança feita fora do editor): não se sabe o que mudou.
        self.assertIsNotNone(conflito(self.oficio, 'v0', 'v3', ['motivo']))
        self.assertIsNone(conflito(self.oficio, 'v3', 'v3', ['motivo']))


class PresencaTests(CenarioOficioMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.oficio = self.criar()
        self.colega = get_user_model().objects.create_user(username='colega', first_name='Fulana', last_name='Silva', deve_trocar_senha=False)
        self.colega.setores.add(self.setor)
        self.colega.groups.set(self.user.groups.all())

    def test_a_barra_diz_quem_mais_esta_no_documento(self):
        url = reverse('documentos:editor_presenca', args=['oficio', self.oficio.pk])
        self.assertEqual(self.client.post(url, data='{}', content_type='application/json').json()['outros'], [])
        self.client.force_login(self.colega)
        self.assertEqual(self.client.post(url, data='{}', content_type='application/json').json()['outros'], ['operador-f4'])
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url, data='{}', content_type='application/json').json()['outros'], ['Fulana Silva'])
        # A colega fechou o documento.
        self.client.force_login(self.colega)
        self.client.post(url, data='{"sair": true}', content_type='application/json')
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url, data='{}', content_type='application/json').json()['outros'], [])

    def test_quem_nao_avisa_ha_um_minuto_some(self):
        marcar_presenca('oficio', self.oficio.pk, self.colega)
        chave = f'editor:presenca:oficio:{self.oficio.pk}:'
        dados = cache.get(chave)
        dados[str(self.colega.pk)]['visto'] = '2020-01-01T00:00:00+00:00'
        cache.set(chave, dados, 120)
        self.assertEqual(marcar_presenca('oficio', self.oficio.pk, self.user), [])

    def test_a_pagina_do_editor_leva_a_url_da_presenca(self):
        r = self.client.get(reverse('documentos:editor_embutido', args=['oficio', self.oficio.pk]))
        self.assertContains(r, 'data-de-url-presenca=')
        self.assertContains(r, 'data-de-presenca')
