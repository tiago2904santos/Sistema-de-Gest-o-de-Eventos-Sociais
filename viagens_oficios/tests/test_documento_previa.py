"""O documento do ofício no fim do formulário: o editor embutido (a folha A4
editável, que é o visualizador) e a folha em si.

A folha é o mesmo HTML que vira PDF, no modo `editor`, com os trechos do
registro de campos editáveis marcados para quem pode editar. O endereço
antigo da tela do documento leva ao formulário, no cartão do documento.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .fixtures import CenarioOficioMixin


class PreviaDoDocumentoTests(CenarioOficioMixin, TestCase):
    def embutido(self, o):
        return self.client.get(reverse('documentos:editor_embutido', args=['oficio', o.pk]))

    def test_editor_embutido_traz_a_folha_e_o_pdf(self):
        o = self.criar()
        r = self.embutido(o)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, reverse('documentos:editor_folha', args=['oficio', o.pk]))
        self.assertContains(r, 'data-de-pdf="' + reverse('viagens_oficios:gerar', args=[o.pk, 'oficio', 'pdf']))
        self.assertNotContains(r, 'dc-aviso')
        # Nada de <form> no editor: ele mora dentro do formulário do ofício.
        self.assertNotContains(r, '<form')

    def test_editor_avisa_pendencias_e_esconde_a_emissao(self):
        o = self.criar()
        o.motivo = ''
        o.save(update_fields=['motivo', 'atualizado_em'])
        r = self.embutido(o)
        self.assertContains(r, 'dc-aviso')
        self.assertNotContains(r, 'data-de-pdf')

    def test_endereco_antigo_leva_ao_formulario_no_cartao(self):
        o = self.criar()
        destino = reverse('viagens_oficios:editar', args=[o.pk]) + '#documento-oficio'
        self.assertRedirects(self.client.get(reverse('viagens_oficios:documento', args=[o.pk])), destino, fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse('documentos:editor_pagina', args=['oficio', o.pk])), destino, fetch_redirect_response=False)

    def test_folha_e_o_documento_em_modo_editor_com_os_campos_do_registro(self):
        o = self.criar()
        r = self.client.get(reverse('documentos:editor_folha', args=['oficio', o.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['X-Frame-Options'], 'SAMEORIGIN')
        html = r.content.decode()
        for trecho in ['documento--editor', 'class="folha"', '/static/img/brasao-pcpr.png', '<style>',
                       'POLÍCIA CIVIL DO PARANÁ', o.numero_formatado, 'Ana Teste', 'Missão F4', 'Londrina/PR']:
            self.assertIn(trecho, html)
        self.assertIn('data-doc-campo="motivo"', html)  # operador: os campos do registro vêm marcados

    def test_formulario_do_oficio_traz_o_editor_no_fim(self):
        o = self.criar()
        r = self.client.get(reverse('viagens_oficios:editar', args=[o.pk]))
        self.assertContains(r, 'id="documento-oficio"')
        self.assertContains(r, 'data-de-embutir="' + reverse('documentos:editor_embutido', args=['oficio', o.pk]) + '"')
        self.assertContains(r, 'js/documento-embutido.js')

    def test_sem_acesso_ao_modulo_nao_ve_a_folha(self):
        o = self.criar()
        fora = get_user_model().objects.create_user(username='fora', deve_trocar_senha=False)
        self.client.force_login(fora)
        for nome in ['documento', 'documento_folha']:
            self.assertIn(self.client.get(reverse(f'viagens_oficios:{nome}', args=[o.pk])).status_code, (302, 403, 404))
        self.assertIn(self.embutido(o).status_code, (302, 403))
