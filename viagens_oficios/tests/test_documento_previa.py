"""Prévia A4 do ofício: a página que embute a folha e a folha em si.

A folha é o mesmo HTML que vira PDF, no modo `editor`, com os trechos do
registro de campos editáveis marcados para quem pode editar.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .fixtures import CenarioOficioMixin


class PreviaDoDocumentoTests(CenarioOficioMixin, TestCase):
    def test_pagina_embute_a_folha_e_leva_de_volta_ao_oficio(self):
        o = self.criar()
        r = self.client.get(reverse('viagens_oficios:documento', args=[o.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, reverse('viagens_oficios:documento_folha', args=[o.pk]))
        self.assertContains(r, reverse('viagens_oficios:editar', args=[o.pk]))
        self.assertContains(r, 'Baixar PDF')
        self.assertNotContains(r, 'dc-aviso')

    def test_pagina_avisa_pendencias_e_esconde_a_emissao(self):
        o = self.criar()
        o.motivo = ''
        o.save(update_fields=['motivo', 'atualizado_em'])
        r = self.client.get(reverse('viagens_oficios:documento', args=[o.pk]))
        self.assertContains(r, 'dc-aviso')
        self.assertNotContains(r, 'Baixar PDF')

    def test_folha_e_o_documento_em_modo_editor_com_os_campos_do_registro(self):
        o = self.criar()
        r = self.client.get(reverse('viagens_oficios:documento_folha', args=[o.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['X-Frame-Options'], 'SAMEORIGIN')
        html = r.content.decode()
        for trecho in ['documento--editor', 'class="folha"', '/static/img/brasao-pcpr.png', '<style>',
                       'POLÍCIA CIVIL DO PARANÁ', o.numero_formatado, 'Ana Teste', 'Missão F4', 'Londrina/PR']:
            self.assertIn(trecho, html)
        self.assertIn('data-doc-campo="motivo"', html)  # operador: os campos do registro vêm marcados

    def test_formulario_do_oficio_leva_a_previa(self):
        o = self.criar()
        r = self.client.get(reverse('viagens_oficios:editar', args=[o.pk]))
        self.assertContains(r, reverse('viagens_oficios:documento', args=[o.pk]))

    def test_sem_acesso_ao_modulo_nao_ve_a_folha(self):
        o = self.criar()
        fora = get_user_model().objects.create_user(username='fora', deve_trocar_senha=False)
        self.client.force_login(fora)
        for nome in ['documento', 'documento_folha']:
            self.assertIn(self.client.get(reverse(f'viagens_oficios:{nome}', args=[o.pk])).status_code, (302, 403))
