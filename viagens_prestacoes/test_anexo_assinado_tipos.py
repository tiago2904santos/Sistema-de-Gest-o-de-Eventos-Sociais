"""Caracterização do anexo assinado na etapa Documentos.

A etapa Documentos oferece **cinco** anexos assinados no mesmo modal: despacho,
ofício, relatório técnico, diário de bordo e comprovante. Cada cartão V2 leva
ao modal sua própria URL e seus dados atuais, sem depender de uma posição numa
lista compartilhada.

Estes testes fotografam o que a tela entrega hoje — quais URLs de upload, quais
rótulos e quais anexos atuais chegam ao HTML para cada um dos cinco tipos. Eles
existem para provar que a troca de ordinal por chave semântica no `H-03` não
muda nada além do nome: as mesmas cinco URLs, os mesmos cinco rótulos.

O que este arquivo NÃO fixa de propósito: o nome do atributo nem o formato do
payload. Fixar isso aqui travaria justamente o que o `H-03` vem trocar.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin

class AnexoAssinadoTiposTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.ps = self.fixture.prestacoes_servidor[0]
        self.url = reverse('viagens_prestacoes:documentos_servidor', args=[self.ps.pk])

    def _contexto(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response

    def test_a_etapa_documentos_oferece_exatamente_cinco_tipos_de_anexo(self):
        """Cinco documentos assinados distintos, não cinco posições numa lista."""
        kinds = self._contexto().context['attach_kinds']
        self.assertEqual(len(kinds), 5)

    def test_cada_tipo_traz_url_de_upload_propria_e_nao_repetida(self):
        """URLs distintas são o contrato de verdade: é onde o arquivo vai parar."""
        kinds = self._contexto().context['attach_kinds']
        urls = [k['url'] for k in self._iterar(kinds)]
        self.assertEqual(len(urls), 5)
        self.assertEqual(len(set(urls)), 5, f'URL repetida entre tipos: {urls}')
        for url in urls:
            self.assertTrue(url.startswith('/'), url)

    def test_os_cinco_rotulos_de_opcao_sao_os_documentos_do_fluxo(self):
        kinds = self._contexto().context['attach_kinds']
        rotulos = sorted((k['option_label'] for k in self._iterar(kinds)))
        self.assertEqual(rotulos, ['Comprovante', 'DB', 'Despacho', 'Ofício', 'RT'])

    def test_cada_tipo_descreve_o_documento_em_texto_para_o_modal(self):
        """`doc_label` é a frase que o modal mostra — sem ela o usuário não sabe o que anexa."""
        kinds = self._contexto().context['attach_kinds']
        for kind in self._iterar(kinds):
            with self.subTest(rotulo=kind['option_label']):
                self.assertTrue(kind['doc_label'].strip(), kind)

    def test_sem_anexo_ainda_os_campos_de_arquivo_atual_vem_vazios(self):
        kinds = self._contexto().context['attach_kinds']
        for kind in self._iterar(kinds):
            with self.subTest(rotulo=kind['option_label']):
                self.assertFalse(kind['current_name'])

    def test_cinco_formularios_v32_de_upload_tem_csrf(self):
        import re
        # Fora o modal de anexar assinado do shell, que existe em toda página.
        html = re.sub(r'<dialog class="an-dialogo"[^>]*data-anexar-dialogo.*?</dialog>', '', self._contexto().content.decode(), flags=re.S)
        self.assertEqual(html.count('enctype="multipart/form-data"'), 5)
        self.assertEqual(html.count('class="prestacao-upload"'), 5)
        self.assertGreaterEqual(html.count('name="csrfmiddlewaretoken"'), 5)

    def test_o_html_carrega_as_cinco_urls_de_upload(self):
        """Prova de ponta a ponta: as 5 URLs do contexto chegam ao HTML entregue.

        É esta asserção que sustenta o `H-03`: qualquer que seja o formato em que
        as URLs viajem — 30 atributos planos hoje, um JSON depois — elas têm de
        continuar todas presentes.
        """
        response = self._contexto()
        html = response.content.decode()
        for kind in response.context['uploads']:
            with self.subTest(rotulo=kind['titulo']):
                self.assertIn(kind['url'], html)

    @staticmethod
    def _iterar(kinds):
        """Aceita dict (ordinais, hoje) ou lista (chaves semânticas, depois do H-03)."""
        return list(kinds.values()) if hasattr(kinds, 'values') else list(kinds)
