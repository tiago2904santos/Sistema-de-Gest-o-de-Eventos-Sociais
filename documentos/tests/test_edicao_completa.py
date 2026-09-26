"""Edição completa de documento e textos dos modelos (m057).

O documento inteiro (cabeçalho, corpo, rodapé) editado à mão vira uma versão
editada: sanitizada, versionada, usada no PDF/DOCX até voltar ao modelo, com
aviso quando os dados mudam depois. Os textos-base do modelo de cada tipo
se editam na tela de modelos e valem para os próximos documentos.
"""
import json
from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from documentos.models import DocumentoArtefato, DocumentoAssinaturaVersao, DocumentoVersaoEditada, ModeloTextoDocumento
from documentos.services import edicao_completa as edicao
from documentos.services.document_blocks import conteudo_documental
from documentos.services.document_context import contexto_do_oficio
from documentos.services.pdf_renderer import renderizar_html
from documentos.services.types import DocumentoTipo
from viagens_oficios.tests.fixtures import CenarioOficioMixin


class SanitizacaoTests(SimpleTestCase):
    def test_lista_branca_tira_script_eventos_estilos_perigosos_e_enderecos(self):
        sujo = (
            '<p onclick="roubar()" style="color:red; text-align: center; background:url(javascript:x)" class="doc-x doc-editavel">'
            'Olá <a href="javascript:alert(1)">link</a><script>alert(1)</script><style>p{}</style>'
            '<iframe src="//x"></iframe><input value="1">fim<img src="http://fora/x.png" onerror="x">'
            '<img src="/static/img/brasao-pcpr.png?v=2"></p><!-- comentário -->'
        )
        limpo = edicao.sanitizar(sujo)
        self.assertEqual(limpo, '<p style="text-align: center" class="doc-x">Olá linkfim<img data-imagem="brasao"></p>')

    def test_mantem_formatacao_listas_e_tabelas(self):
        html = ('<h1>T</h1><p style="text-align: justify">a <b>b</b> <i>c</i> <u>d</u> <s>e</s><br>f</p>'
                '<ul><li>1</li></ul><ol><li>2</li></ol>'
                '<table class="doc-tabela-livre"><tr><th colspan="2">x</th></tr><tr><td rowspan="999">y</td></tr></table>')
        limpo = edicao.sanitizar(html)
        for trecho in ('<h1>T</h1>', '<b>b</b>', '<i>c</i>', '<u>d</u>', '<s>e</s>', '<br>', '<ul><li>1</li></ul>',
                       '<th colspan="2">x</th>', '<td>y</td>', 'class="doc-tabela-livre"'):
            self.assertIn(trecho, limpo)

    def test_tags_abertas_sao_fechadas_e_align_vira_estilo(self):
        self.assertEqual(edicao.sanitizar('<div align="right"><p>x'), '<div style="text-align: right"><p>x</p></div>')
        self.assertEqual(edicao.sanitizar('<p>a<script>b'), '<p>a</p>')

    def test_regioes_desconhecidas_ou_grandes_nao_passam(self):
        self.assertEqual(edicao.sanitizar_regioes({'corpo': '<p>x</p>', 'outra': '<p>y</p>'}), {'corpo': '<p>x</p>'})
        with self.assertRaises(ValueError):
            edicao.sanitizar_regioes({'corpo': 'x' * (edicao.TAMANHO_MAXIMO_REGIAO + 1)})
        with self.assertRaises(ValueError):
            edicao.sanitizar_regioes({'corpo': ['x']})

    def test_aplicar_troca_so_a_regiao_e_resolve_as_imagens(self):
        folha = '<header><!--ed:cabecalho--><img src="a"><p>X</p><!--/ed:cabecalho--></header><main><!--ed:corpo--><p>velho \\1</p><!--/ed:corpo--></main>'
        nova = edicao.aplicar_regioes(folha, {'corpo': '<p>novo \\1</p><img data-imagem="marca">'}, {'marca': '/static/m.png'})
        self.assertIn('<p>X</p>', nova)
        self.assertIn('<!--ed:corpo--><p>novo \\1</p><img src="/static/m.png" data-imagem="marca"><!--/ed:corpo-->', nova)
        self.assertEqual(edicao.extrair_regioes(nova)['corpo'], '<p>novo \\1</p><img src="/static/m.png" data-imagem="marca">')
        # O hash olha o texto, não o CSS nem as marcas.
        self.assertEqual(edicao.impressao_digital(folha), edicao.impressao_digital(folha.replace('<p>', '<p class="z">')))
        self.assertNotEqual(edicao.impressao_digital(folha), edicao.impressao_digital(nova))

    def test_docx_da_versao_editada(self):
        from docx import Document

        from documentos.services.html_docx import regioes_para_docx

        conteudo = regioes_para_docx({
            'cabecalho': '<img data-imagem="brasao"><p>POLÍCIA CIVIL</p>',
            'corpo': '<h1>Título</h1><p style="text-align: justify">Texto <b>forte</b></p><ul><li>item</li></ul>'
                     '<table><tr><td>a</td><td>b</td></tr></table>',
            'rodape': '<p>Rodapé livre</p>',
        })
        documento = Document(BytesIO(conteudo))
        textos = [p.text for p in documento.paragraphs]
        self.assertEqual(textos[:3], ['Título', 'Texto forte', 'item'])
        self.assertEqual([c.text for c in documento.tables[0].rows[0].cells], ['a', 'b'])
        self.assertIn('POLÍCIA CIVIL', [p.text for p in documento.sections[0].header.paragraphs])
        self.assertIn('Rodapé livre', [p.text for p in documento.sections[0].footer.paragraphs])


class EdicaoCompletaTests(CenarioOficioMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.oficio = self.criar()

    def url(self, nome, chave='oficio', pk=None, v='', *args):
        url = reverse(f'documentos:{nome}', args=[chave, pk or self.oficio.pk, *args])
        return f'{url}?v={v}' if v else url

    def salvar(self, regioes, *, chave='oficio', pk=None, v='', estado=None):
        if estado is None:
            atual = DocumentoVersaoEditada.objects.order_by('-criado_em', '-pk').filter(tipo_documento=DocumentoTipo(
                {'termo_oficio': 'termo_autorizacao'}.get(chave, chave)).value, variante=v).first()
            estado = atual.pk if atual else ''
        return self.client.post(self.url('editor_completo_salvar', chave, pk, v), data=json.dumps({'estado': estado, 'regioes': regioes}),
                                content_type='application/json')

    def html_pdf(self):
        return renderizar_html(DocumentoTipo.OFICIO, contexto_do_oficio(self.oficio, modo='pdf'), modo='pdf')

    def test_pagina_e_folha_abrem_com_as_regioes_marcadas(self):
        r = self.client.get(self.url('editor_completo'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-dcp-editavel')
        folha = self.client.get(self.url('editor_completo_folha')).content.decode()
        for regiao in ('cabecalho', 'corpo', 'rodape'):
            self.assertIn(f'<!--ed:{regiao}-->', folha)
        self.assertNotIn('data-doc-campo', folha)  # a folha do editor completo não é a de campos
        self.assertIn('Missão F4', folha)
        # O editor de campos oferece o editor completo.
        self.assertContains(self.client.get(self.url('editor_embutido')), self.url('editor_completo'))

    def test_salvar_grava_sanitizado_e_o_pdf_sai_da_versao_editada(self):
        r = self.salvar({'corpo': '<p>Texto <b>livre</b> do ofício<script>x()</script></p>', 'cabecalho': '<p onclick="x">CABEÇALHO NOVO</p>'})
        self.assertEqual(r.status_code, 200, r.content)
        versao = DocumentoVersaoEditada.objects.get()
        self.assertEqual(versao.regioes['corpo'], '<p>Texto <b>livre</b> do ofício</p>')
        self.assertEqual(versao.regioes['cabecalho'], '<p>CABEÇALHO NOVO</p>')
        self.assertEqual(versao.criado_por, self.user)
        self.assertTrue(versao.impressao_base)
        html = self.html_pdf()
        self.assertIn('Texto <b>livre</b> do ofício', html)
        self.assertIn('CABEÇALHO NOVO', html)
        self.assertNotIn('Missão F4', html)
        # O rodapé não foi mandado: continua o do modelo.
        self.assertIn('doc-rodape__unidade', html)
        # Entra no payload de geração (e, por ele, na chave de cache).
        self.assertEqual(conteudo_documental(DocumentoTipo.OFICIO, self.oficio)['versao_editada']['id'], versao.pk)
        with self.assertRaises(ValidationError):
            versao.save()  # imutável

    def test_geracao_real_usa_a_versao_editada_no_pdf_e_no_docx(self):
        from docx import Document

        from documentos.services.types import DocumentoFormato
        from viagens_oficios.document_generation import gerar_documento

        self.salvar({'corpo': '<p>Corpo editado para o DOCX</p>'})
        docx = gerar_documento(self.oficio, DocumentoFormato.DOCX)
        self.assertIn('Corpo editado para o DOCX', [p.text for p in Document(BytesIO(docx.conteudo)).paragraphs])
        artefato = DocumentoArtefato.objects.get(pk=docx.artefato_id)
        self.assertIn('versao_editada', artefato.payload_snapshot['documento'])

    def test_conflito_quando_outra_pessoa_gravou_antes(self):
        self.assertEqual(self.salvar({'corpo': '<p>um</p>'}).status_code, 200)
        r = self.salvar({'corpo': '<p>dois</p>'}, estado='')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(DocumentoVersaoEditada.objects.count(), 1)

    def test_aviso_de_desatualizada_quando_os_dados_mudam(self):
        from documentos.editor.completo import situacao_da_edicao
        from documentos.editor.vinculos import vinculo_do_tipo

        self.salvar({'corpo': '<p>editado</p>'})
        vinculo = vinculo_do_tipo('oficio')
        self.assertFalse(situacao_da_edicao(vinculo, vinculo.carregar(self.oficio.pk))['desatualizada'])
        type(self.oficio).objects.filter(pk=self.oficio.pk).update(motivo='Outro motivo depois da edição')
        self.assertTrue(situacao_da_edicao(vinculo, vinculo.carregar(self.oficio.pk))['desatualizada'])
        self.assertContains(self.client.get(self.url('editor_completo')), 'Os dados mudaram depois desta edição')
        self.assertContains(self.client.get(self.url('editor_embutido')), 'Os dados mudaram depois da edição completa')

    def test_voltar_ao_modelo_e_restaurar_guardam_o_historico(self):
        self.salvar({'corpo': '<p>primeira</p>'})
        primeira = DocumentoVersaoEditada.objects.get()
        self.salvar({'corpo': '<p>segunda</p>'})
        r = self.client.post(self.url('editor_completo_modelo'))
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(edicao.vigente(DocumentoTipo.OFICIO, self.oficio))
        self.assertIn('Missão F4', self.html_pdf())
        r = self.client.post(self.url('editor_completo_restaurar', 'oficio', None, '', primeira.pk))
        self.assertEqual(r.status_code, 302)
        vigente = edicao.vigente(DocumentoTipo.OFICIO, self.oficio)
        self.assertEqual((vigente.acao, vigente.restaurada_de, vigente.regioes['corpo']), ('restauracao', primeira, '<p>primeira</p>'))
        self.assertIn('primeira', self.html_pdf())
        self.assertEqual(DocumentoVersaoEditada.objects.count(), 4)
        pagina = self.client.get(self.url('editor_completo'))
        self.assertContains(pagina, 'Voltou ao modelo')
        self.assertContains(pagina, 'Restaurar esta versão')

    def test_quem_so_consulta_ve_mas_nao_grava(self):
        leitor = get_user_model().objects.create_user(username='leitor-m057', deve_trocar_senha=False)
        leitor.setores.add(self.setor)
        self.client.force_login(leitor)
        pagina = self.client.get(self.url('editor_completo'))
        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, 'data-dcp-editavel')
        self.assertEqual(self.salvar({'corpo': '<p>x</p>'}).status_code, 403)
        self.assertEqual(self.client.post(self.url('editor_completo_modelo')).status_code, 403)
        self.assertFalse(DocumentoVersaoEditada.objects.exists())

    def test_documento_assinado_so_se_edita_reabrindo(self):
        artefato = DocumentoArtefato.objects.create(tipo='oficio', formato='pdf', oficio=self.oficio, hash_sha256='0' * 64,
                                                    arquivo=ContentFile(b'%PDF-1.4', name='o.pdf'))
        versao = DocumentoAssinaturaVersao.objects.create(artefato=artefato, arquivo=ContentFile(b'%PDF-1.4 a', name='a.pdf'),
                                                          hash_sha256='1' * 64)
        r = self.salvar({'corpo': '<p>x</p>'})
        self.assertEqual(r.status_code, 403)
        self.assertIn('versão assinada', r.json()['mensagem'])
        self.assertContains(self.client.get(self.url('editor_completo')), 'Só leitura')
        versao.revogada_em = versao.criado_em
        versao.save()
        self.assertEqual(self.salvar({'corpo': '<p>x</p>'}).status_code, 200)

    def test_cancelado_nao_edita(self):
        type(self.oficio).objects.filter(pk=self.oficio.pk).update(cancelado=True)
        self.assertEqual(self.salvar({'corpo': '<p>x</p>'}).status_code, 403)

    def test_termo_de_um_servidor_nao_muda_o_do_outro(self):
        from viagens_termos.models import TermoAutorizacao

        termo = TermoAutorizacao.objects.create(oficio=self.oficio, destino_estado=self.uf, destino_cidade=self.destino,
                                                data_evento_inicio=date(2026, 9, 10), viatura=self.viatura)
        termo.servidores.set([self.a, self.b])
        r = self.salvar({'corpo': '<p>Termo só da Ana</p>'}, chave='termo_autorizacao', pk=termo.pk, v=str(self.a.pk))
        self.assertEqual(r.status_code, 200, r.content)
        folha_a = self.client.get(self.url('editor_completo_folha', 'termo_autorizacao', termo.pk, str(self.a.pk))).content.decode()
        folha_b = self.client.get(self.url('editor_completo_folha', 'termo_autorizacao', termo.pk, str(self.b.pk))).content.decode()
        self.assertIn('Termo só da Ana', folha_a)
        self.assertNotIn('Termo só da Ana', folha_b)
        # A geração do termo do cadastro usa a mesma variante do editor.
        from viagens_termos.services import build_termo_cadastro_payload, _conteudo_documental, variante_do_termo_cadastro

        self.assertIn('versao_editada', _conteudo_documental(termo, variante_do_termo_cadastro(self.a)))
        self.assertNotIn('versao_editada', _conteudo_documental(termo, variante_do_termo_cadastro(self.b)))
        self.assertTrue(build_termo_cadastro_payload(termo, self.a))

    def test_todos_os_documentos_de_viagens_abrem_no_editor_completo(self):
        from documentos.editor.vinculos import VINCULOS

        for chave in ('oficio', 'justificativa', 'termo_oficio'):
            with self.subTest(chave=chave):
                v = str(self.a.pk) if chave == 'termo_oficio' else ''
                folha = self.client.get(self.url('editor_completo_folha', chave, self.oficio.pk, v))
                self.assertEqual(folha.status_code, 200)
                self.assertIn('<!--ed:corpo-->', folha.content.decode())
        # Todo vínculo registrado tem a folha completa (os do Coffee Break incluídos).
        for vinculo in VINCULOS.values():
            self.assertTrue(callable(getattr(vinculo, 'html_documento', None)))


class ModelosDeTextoTests(CenarioOficioMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.oficio = self.criar()
        self.user.groups.add(Group.objects.get(name='VIAGENS_GESTOR'))
        self.url = reverse('documentos:modelos_tipo', args=['termo_autorizacao'])

    def html_termo(self):
        from documentos.services.document_context import contexto_de_payload
        from viagens_oficios.documents import build_termo_payload
        from viagens_termos.services import _conteudo_documental, _legacy_docx_context

        payload = build_termo_payload(self.oficio, self.a)
        payload['documento'] = _conteudo_documental(self.oficio, str(self.a.pk))
        contexto = contexto_de_payload(DocumentoTipo.TERMO_AUTORIZACAO, payload, _legacy_docx_context(payload))
        return renderizar_html(DocumentoTipo.TERMO_AUTORIZACAO, contexto, modo='pdf')

    def test_sem_alteracao_o_termo_sai_com_o_texto_de_sempre(self):
        html = self.html_termo()
        self.assertIn('manifesto o interesse em participar do PCPR na Comunidade, <strong>', html)
        self.assertIn('</strong> para execução de atividades inerentes à Assessoria de Comunicação Social - ASCOM/PCPR.', html)

    def test_gestor_reescreve_o_texto_do_termo_com_campos_automaticos(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Texto da manifestação')
        self.assertContains(r, '{periodo}')
        r = self.client.post(self.url, {'texto__texto': 'declaro participar da Operação Verão em {destino}, {periodo}, lotado em {unidade}. {xyz}'})
        self.assertEqual(r.status_code, 302)
        linha = ModeloTextoDocumento.objects.get(chave='texto')
        self.assertEqual((linha.tipo_documento, linha.criado_por), ('termo_autorizacao', self.user))
        html = self.html_termo()
        self.assertIn('declaro participar da Operação Verão em <strong>Londrina/PR</strong>, <strong>', html)
        self.assertIn('lotado em UNIDADE F4.', html)
        self.assertIn('{xyz}', html)
        self.assertNotIn('PCPR na Comunidade', html)
        self.assertContains(self.client.get(self.url), 'Marcador que este texto não preenche')
        # Gravar de novo o mesmo texto não acumula linhas; voltar ao padrão, sim.
        self.client.post(self.url, {'texto__texto': linha.texto})
        self.assertEqual(ModeloTextoDocumento.objects.count(), 1)
        self.client.post(self.url, {'padrao': 'texto'})
        self.assertIn('PCPR na Comunidade', self.html_termo())
        self.assertEqual(ModeloTextoDocumento.objects.count(), 2)
        self.client.post(self.url, {'usar': linha.pk})
        self.assertIn('Operação Verão', self.html_termo())

    def test_texto_do_modelo_nao_passa_por_cima_do_reescrito_no_documento_nem_da_versao_editada(self):
        from documentos.services.document_blocks import gravar_override

        self.client.post(reverse('documentos:modelos_tipo', args=['oficio']), {'texto__fecho': 'Atenciosamente,'})
        self.assertIn('Atenciosamente,', renderizar_html(DocumentoTipo.OFICIO, contexto_do_oficio(self.oficio, modo='pdf'), modo='pdf'))
        gravar_override(DocumentoTipo.OFICIO, self.oficio, 'fecho', 'Cordialmente,', self.user)
        html = renderizar_html(DocumentoTipo.OFICIO, contexto_do_oficio(self.oficio, modo='pdf'), modo='pdf')
        self.assertIn('Cordialmente,', html)
        self.assertNotIn('Atenciosamente,', html)

    def test_so_o_gestor_administra_os_modelos(self):
        self.user.groups.remove(Group.objects.get(name='VIAGENS_GESTOR'))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {'texto__texto': 'x'}).status_code, 403)
        self.assertFalse(ModeloTextoDocumento.objects.exists())
        self.assertEqual(self.client.get(reverse('documentos:modelos_tipo', args=['nao_existe'])).status_code, 404)
