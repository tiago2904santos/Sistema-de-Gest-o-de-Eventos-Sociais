"""Blocos documentais: override de parágrafo do modelo, restauração, quebras
de página em pontos registrados, entrada no payload (cache) e auditoria.
"""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from documentos.editor.blocos import BLOCOS_OFICIO
from documentos.models import DocumentoBloco
from documentos.services.document_context import contexto_do_oficio
from documentos.services.pdf_renderer import renderizar_html
from documentos.services.types import DocumentoTipo
from viagens_oficios.tests.fixtures import CenarioOficioMixin

PADRAO = next(b for b in BLOCOS_OFICIO if b.chave == "declaracao_cartao").padrao


class BlocosDocumentaisTests(CenarioOficioMixin, TestCase):
    def url_bloco(self, o, chave='declaracao_cartao'):
        return reverse('documentos:editor_bloco', args=['oficio', o.pk, chave])

    def url_quebra(self, o, chave):
        return reverse('documentos:editor_quebra', args=['oficio', o.pk, chave])

    def patch_bloco(self, o, conteudo, versao=None):
        if versao is None:  # como o painel faz: a versão vem do GET que o abriu
            versao = self.client.get(self.url_bloco(o)).json()['versao']
        return self.client.patch(self.url_bloco(o), data=json.dumps({'versao': versao, 'valores': {'conteudo': conteudo}}), content_type='application/json')

    def folha(self, o):
        return self.client.get(reverse('viagens_oficios:documento_folha', args=[o.pk])).content.decode()

    def html_pdf(self, o):
        return renderizar_html(DocumentoTipo.OFICIO, contexto_do_oficio(o, modo='pdf'), modo='pdf')

    def test_sem_override_o_texto_e_o_do_registro_na_folha_e_no_pdf(self):
        o = self.criar()
        self.assertIn(PADRAO, self.folha(o))
        self.assertIn(PADRAO, self.html_pdf(o))
        painel = self.client.get(self.url_bloco(o)).json()
        self.assertIn(PADRAO, painel['fragmento'])
        self.assertNotIn('data-de-restaurar', painel['fragmento'])
        self.assertEqual(painel['versao'], '')

    def test_override_vale_na_folha_e_no_pdf_escapado_e_marcado(self):
        o = self.criar()
        r = self.patch_bloco(o, 'Declaro <b>outra</b> coisa.\r\nSegunda linha.')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['editado'])
        bloco = DocumentoBloco.objects.get(oficio=o, chave='declaracao_cartao')
        self.assertEqual((bloco.conteudo_original, bloco.editado_manualmente, bloco.editado_por), (PADRAO, True, self.user))
        folha = self.folha(o)
        self.assertIn('Declaro &lt;b&gt;outra&lt;/b&gt; coisa.<br>Segunda linha.', folha)
        self.assertIn('data-doc-override="1"', folha)
        self.assertNotIn(PADRAO, folha)
        pdf = self.html_pdf(o)
        self.assertIn('Declaro &lt;b&gt;outra&lt;/b&gt; coisa.<br>Segunda linha.', pdf)
        self.assertNotIn('data-doc', pdf)
        painel = self.client.get(self.url_bloco(o)).json()
        self.assertIn('data-de-restaurar', painel['fragmento'])
        self.assertIn('Texto alterado por', painel['fragmento'])
        self.assertEqual(painel['versao'], bloco.atualizado_em.isoformat())

    def test_restaurar_por_delete_por_texto_vazio_ou_igual_ao_modelo(self):
        o = self.criar()
        for restaurar in (lambda: self.client.delete(self.url_bloco(o)), lambda: self.patch_bloco(o, '   '), lambda: self.patch_bloco(o, PADRAO)):
            self.patch_bloco(o, 'Texto alterado.')
            r = restaurar()
            self.assertEqual(r.status_code, 200, r.content)
            self.assertFalse(r.json()['editado'])
            bloco = DocumentoBloco.objects.get(oficio=o, chave='declaracao_cartao')
            self.assertEqual((bloco.editado_manualmente, bloco.conteudo_atual), (False, PADRAO))
            self.assertIn(PADRAO, self.folha(o))

    def test_override_entra_no_payload_da_geracao_e_portanto_na_chave_de_cache(self):
        from viagens_oficios.document_generation import gerar_documento
        from documentos.services.types import DocumentoFormato
        o = self.criar()
        self.patch_bloco(o, 'Texto alterado.')
        with mock.patch('viagens_oficios.document_generation.DocumentoFacade.gerar') as gerar:
            gerar_documento(o, DocumentoFormato.PDF)
        documento = gerar.call_args.kwargs['payload']['documento']
        self.assertEqual(documento['blocos']['declaracao_cartao']['conteudo'], 'Texto alterado.')
        self.assertTrue(documento['blocos']['declaracao_cartao']['editado'])
        self.assertEqual(documento['quebras'], [])

    def test_quebra_de_pagina_so_em_ponto_registrado(self):
        o = self.criar()
        self.assertEqual(self.client.patch(self.url_quebra(o, 'qualquer'), data='{"ativa": true}', content_type='application/json').status_code, 404)
        self.assertEqual(self.client.patch(self.url_quebra(o, 'apos_roteiro'), data='{"ativa": "sim"}', content_type='application/json').status_code, 400)
        r = self.client.patch(self.url_quebra(o, 'apos_roteiro'), data='{"ativa": true}', content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        folha = self.folha(o)
        self.assertIn('data-doc-quebra="apos_roteiro" data-doc-quebra-ativa="1"', folha)
        self.assertIn('class="doc-quebra-slot" data-doc-quebra="apos_equipe"', folha)
        self.assertIn('<div class="doc-quebra"></div>', self.html_pdf(o))
        r = self.client.patch(self.url_quebra(o, 'apos_roteiro'), data='{"ativa": false}', content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('data-doc-quebra-ativa', self.folha(o))
        self.assertNotIn('doc-quebra"', self.html_pdf(o))
        self.assertFalse(DocumentoBloco.objects.filter(oficio=o, tipo='quebra_pagina').exists())

    def test_versao_antiga_e_409(self):
        o = self.criar()
        self.patch_bloco(o, 'Primeiro.')
        r = self.patch_bloco(o, 'Segundo.', versao='2020-01-01T00:00:00')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(DocumentoBloco.objects.get(oficio=o, chave='declaracao_cartao').conteudo_atual, 'Primeiro.')

    def test_bloco_fora_do_registro_e_404_e_corpo_estranho_e_400(self):
        o = self.criar()
        self.assertEqual(self.client.get(self.url_bloco(o, 'motivo')).status_code, 404)
        r = self.client.patch(self.url_bloco(o), data=json.dumps({'valores': {'conteudo': 'x', 'outro': 'y'}}), content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_auditoria_registra_o_override_com_origem_editor(self):
        o = self.criar()
        with self.captureOnCommitCallbacks(execute=True):
            self.patch_bloco(o, 'Texto alterado.')
        registro = RegistroAuditoria.objects.filter(modelo='documentos.documentobloco', origem='editor').latest('criado_em')
        self.assertEqual(registro.usuario, self.user)
        self.assertEqual(registro.alteracoes['novo']['conteudo_atual'], 'Texto alterado.')

    def test_quem_so_consulta_nao_ve_marcacao_nem_edita(self):
        o = self.criar()
        self.patch_bloco(o, 'Texto alterado.')
        leitor = get_user_model().objects.create_user(username='leitor', deve_trocar_senha=False)
        leitor.setores.add(self.setor)
        self.client.force_login(leitor)
        folha = self.folha(o)
        self.assertIn('Texto alterado.', folha)  # o override vale para todos
        self.assertNotIn('data-doc-bloco', folha)
        self.assertNotIn('class="doc-quebra-slot"', folha)
        self.assertEqual(self.client.get(self.url_bloco(o)).status_code, 403)
        self.assertEqual(self.patch_bloco(o, 'x', versao='').status_code, 403)
        self.assertEqual(self.client.patch(self.url_quebra(o, 'apos_roteiro'), data='{"ativa": true}', content_type='application/json').status_code, 403)
