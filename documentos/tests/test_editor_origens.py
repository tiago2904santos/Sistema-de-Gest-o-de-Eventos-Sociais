"""Editor documental: todo trecho do documento é editável e muda a sua origem —
o ofício, os marcadores dele, o cadastro do servidor da linha, a prestação e a
configuração do setor. Cada origem valida pelo formulário que já é dela no
sistema e tem a própria permissão."""
import json

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from viagens_cadastros.models import ConfiguracaoSistema
from viagens_oficios.tests.fixtures import CenarioOficioMixin


class EditorPorOrigemTests(CenarioOficioMixin, TestCase):
    def url(self, oficio, chave, objeto=None):
        base = reverse('documentos:editor_campo', args=['oficio', oficio.pk, chave])
        return f'{base}?objeto={objeto}' if objeto else base

    def patch(self, oficio, chave, valores, objeto=None, versao=None):
        corpo = {'valores': valores}
        if versao is not None:
            corpo['versao'] = versao
        return self.client.patch(self.url(oficio, chave, objeto), data=json.dumps(corpo), content_type='application/json')

    def folha(self, oficio):
        return self.client.get(reverse('viagens_oficios:documento_folha', args=[oficio.pk])).content.decode()

    def test_a_folha_marca_todos_os_trechos_com_a_origem(self):
        o = self.criar()
        folha = self.folha(o)
        for chave in ('marcacao', 'transporte', 'motorista', 'roteiro', 'servidor_nome', 'servidor_cpf', 'servidor_cargo', 'solicitacao'):
            self.assertIn(f'data-doc-campo="{chave}"', folha)
        self.assertIn(f'data-doc-campo="servidor_nome" data-doc-parte="nome" data-doc-digitavel="uma" data-doc-origem="servidor" data-doc-objeto="{self.a.pk}"', folha)
        for bloco in ('abertura', 'fecho', 'secretaria', 'declaracao_cartao'):
            self.assertIn(f'data-doc-bloco="{bloco}"', folha)
        # A configuração é da gestão: o operador não a vê marcada.
        self.assertNotIn('data-doc-campo="config_unidade"', folha)

    def test_editar_o_nome_do_servidor_muda_o_cadastro(self):
        o = self.criar()
        r = self.patch(o, 'servidor_nome', {'nome': 'ana teste de souza'}, objeto=self.a.pk)
        self.assertEqual(r.status_code, 200, r.content)
        self.a.refresh_from_db()
        self.assertEqual(self.a.nome, 'ANA TESTE DE SOUZA')  # normalizado pelo formulário do cadastro
        self.assertEqual(r.json()['versao'], self.a.atualizado_em.isoformat())
        self.assertIn('Ana Teste de Souza', r.json()['folha'])

    def test_servidor_fora_da_equipe_e_404(self):
        from viagens_cadastros.models import Servidor

        o = self.criar()
        estranho = Servidor.objects.create(nome='FORA DA EQUIPE')
        self.assertEqual(self.client.get(self.url(o, 'servidor_nome', estranho.pk)).status_code, 404)
        self.assertEqual(self.patch(o, 'servidor_nome', {'nome': 'X'}, objeto=estranho.pk).status_code, 404)

    def test_cpf_invalido_volta_com_o_erro_do_cadastro(self):
        o = self.criar()
        r = self.patch(o, 'servidor_cpf', {'cpf': '123'}, objeto=self.a.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn('cpf', r.json()['erros'])

    def test_versao_do_servidor_protege_contra_edicao_concorrente(self):
        o = self.criar()
        r = self.patch(o, 'servidor_nome', {'nome': 'ANA'}, objeto=self.a.pk, versao='2000-01-01T00:00:00+00:00')
        self.assertEqual(r.status_code, 409)

    def test_marcacao_usa_os_servicos_e_os_marcadores_se_excluem(self):
        o = self.criar()
        self.assertEqual(self.patch(o, 'marcacao', {'tipo_documento': 'retificado'}).status_code, 200)
        o.refresh_from_db()
        self.assertTrue(o.retificado_documento)
        self.patch(o, 'marcacao', {'tipo_documento': 'complementar'})
        o.refresh_from_db()
        self.assertTrue(o.complementar_documento)
        self.assertFalse(o.retificado_documento)
        self.patch(o, 'marcacao', {'tipo_documento': ''})
        o.refresh_from_db()
        self.assertFalse(o.complementar_documento or o.retificado_documento)

    def test_transporte_manual_grava_no_oficio(self):
        o = self.criar()
        r = self.patch(o, 'transporte', {'viatura': '', 'transporte_modelo_manual': 'Spin', 'transporte_placa_manual': 'XYZ1A23'})
        self.assertEqual(r.status_code, 200, r.content)
        o.refresh_from_db()
        self.assertIsNone(o.viatura_id)
        self.assertEqual(o.transporte_placa_manual.replace('-', '').upper(), 'XYZ1A23')

    def test_configuracao_so_para_a_gestao(self):
        o = self.criar()
        self.assertEqual(self.client.get(self.url(o, 'config_destinatario')).status_code, 403)
        self.user.groups.add(Group.objects.get(name='VIAGENS_GESTOR'))
        r = self.patch(o, 'config_destinatario', {'destinatario_oficio_nome': 'Fulano de Tal', 'destinatario_oficio_cargo': 'Delegado Geral Adjunto'})
        self.assertEqual(r.status_code, 200, r.content)
        cfg = ConfiguracaoSistema.para_usuario(self.user)
        self.assertEqual(cfg.destinatario_oficio_nome.upper(), 'FULANO DE TAL')
        self.assertIn('data-doc-campo="config_unidade"', self.folha(o))

    def test_bloco_de_abertura_digitado_igual_ao_modelo_nao_grava_override(self):
        from documentos.services.document_blocks import bloco_gravado
        from documentos.services.types import DocumentoTipo

        o = self.criar()
        url = reverse('documentos:editor_bloco', args=['oficio', o.pk, 'abertura'])
        versao = self.client.get(url).json()['versao']
        texto = ('Senhor Delegado, através deste, solicito autorização e medidas para a concessão de diárias e '
                 'recursos para combustível, conforme cronograma abaixo:')
        r = self.client.patch(url, data=json.dumps({'versao': versao, 'valores': {'conteudo': texto}}), content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        gravado = bloco_gravado(DocumentoTipo.OFICIO, o, 'abertura')
        self.assertFalse(gravado and gravado.editado_manualmente)
