"""Editor documental: registro explícito, API GET/PATCH, validação pelo
formulário do domínio, concorrência, permissão e auditoria com origem.

O cenário é o ofício completo dos testes de viagens; o editor não conhece o
model diretamente, só o vínculo.
"""
import json
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from viagens_oficios.tests.fixtures import CenarioOficioMixin


class EditorDeCamposTests(CenarioOficioMixin, TestCase):
    def url(self, oficio, chave, tipo='oficio'):
        return reverse('documentos:editor_campo', args=[tipo, oficio.pk, chave])

    def patch(self, oficio, chave, valores, versao=None):
        oficio.refresh_from_db()
        corpo = {'valores': valores, 'versao': oficio.atualizado_em.isoformat() if versao is None else versao}
        return self.client.patch(self.url(oficio, chave), data=json.dumps(corpo), content_type='application/json')

    def test_get_devolve_o_painel_com_o_componente_do_tipo_e_o_valor_atual(self):
        o = self.criar()
        r = self.client.get(self.url(o, 'motivo'))
        self.assertEqual(r.status_code, 200)
        dados = r.json()
        self.assertEqual(dados['versao'], o.atualizado_em.isoformat())
        self.assertIn('<textarea', dados['fragmento'])
        self.assertIn('Missão F4', dados['fragmento'])
        self.assertIn('data-de-chave="motivo"', dados['fragmento'])
        custeio = self.client.get(self.url(o, 'custeio')).json()['fragmento']
        self.assertIn('data-custom-select', custeio)
        self.assertIn('data-de-quando="custeio=OUTRA_INSTITUICAO"', custeio)
        viajantes = self.client.get(self.url(o, 'servidores')).json()['fragmento']
        self.assertIn('data-multi-pick', viajantes)
        self.assertIn(f'value="{self.a.pk}" checked', viajantes)

    def test_patch_grava_pelo_formulario_e_responde_a_versao_nova(self):
        o = self.criar()
        antes = o.atualizado_em
        r = self.patch(o, 'motivo', {'motivo': '  Reunião   institucional em Londrina  '})
        self.assertEqual(r.status_code, 200, r.content)
        o.refresh_from_db()
        self.assertEqual(o.motivo, 'Reunião institucional em Londrina')  # normalizado como no cadastro
        self.assertNotEqual(o.atualizado_em, antes)
        self.assertEqual(r.json()['versao'], o.atualizado_em.isoformat())

    def test_o_que_o_editor_grava_aparece_na_folha_e_no_formulario(self):
        o = self.criar()
        self.patch(o, 'protocolo', {'protocolo': '987654321'})
        folha = self.client.get(reverse('viagens_oficios:documento_folha', args=[o.pk])).content.decode()
        self.assertIn('98.765.432-1', folha)
        self.assertContains(self.client.get(reverse('viagens_oficios:editar', args=[o.pk])), '987654321')  # o formulário mostra o valor cru

    def test_gravacao_entra_na_auditoria_com_origem_editor(self):
        o = self.criar()
        with self.captureOnCommitCallbacks(execute=True):
            self.patch(o, 'motivo', {'motivo': 'Diligência'})
        registro = RegistroAuditoria.objects.filter(modelo='viagens_oficios.oficio', objeto_id=str(o.pk), origem='editor').latest('criado_em')
        self.assertEqual(registro.usuario, self.user)
        self.assertEqual(registro.alteracoes['motivo'], {'antes': 'Missão F4', 'depois': 'Diligência'})
        self.assertEqual(registro.acao, RegistroAuditoria.Acao.ATUALIZACAO)

    def test_gravacao_pelo_formulario_tem_origem_formulario(self):
        with self.captureOnCommitCallbacks(execute=True):
            o = self.criar()
        registro = RegistroAuditoria.objects.filter(modelo='viagens_oficios.oficio', objeto_id=str(o.pk)).earliest('criado_em')
        self.assertEqual(registro.origem, 'formulario')

    def test_historico_do_oficio_mostra_origem_e_campos_inclusive_de_blocos(self):
        with self.captureOnCommitCallbacks(execute=True):
            o = self.criar()
            self.patch(o, 'motivo', {'motivo': 'Diligência'})
            url_bloco = reverse('documentos:editor_bloco', args=['oficio', o.pk, 'declaracao_cartao'])
            self.client.patch(url_bloco, data=json.dumps({'versao': '', 'valores': {'conteudo': 'Parágrafo reescrito.'}}), content_type='application/json')
        # O histórico mora na página do documento, que é onde o editor grava.
        r = self.client.get(reverse('viagens_oficios:documento', args=[o.pk]))
        self.assertContains(r, 'Editor documental · motivo')
        self.assertContains(r, 'Criação de bloco documental')
        self.assertContains(r, 'Formulário')  # a criação do ofício, pela tela

    def test_versao_antiga_e_409_e_nada_muda(self):
        o = self.criar()
        r = self.patch(o, 'motivo', {'motivo': 'Outro'}, versao='2020-01-01T00:00:00')
        self.assertEqual(r.status_code, 409)
        self.assertTrue(r.json()['conflito'])
        o.refresh_from_db()
        self.assertEqual(o.motivo, 'Missão F4')

    def test_valor_invalido_e_400_com_o_erro_do_formulario_e_nada_muda(self):
        o = self.criar()
        r = self.patch(o, 'protocolo', {'protocolo': '123'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('9 dígitos', r.json()['erros']['protocolo'][0])
        o.refresh_from_db()
        self.assertEqual(o.protocolo, '123456789')

    def test_dado_antigo_invalido_em_outro_campo_nao_trava_nem_muda(self):
        o = self.criar()
        type(o).objects.filter(pk=o.pk).update(protocolo='5')  # dado legado, fora da regra de hoje
        r = self.patch(o, 'motivo', {'motivo': 'Diligência'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('9 dígitos', r.json()['avisos'][0])
        o.refresh_from_db()
        self.assertEqual((o.motivo, o.protocolo), ('Diligência', '5'))

    def test_so_o_campo_pedido_e_os_derivados_vao_ao_banco(self):
        o = self.criar()
        # Dado que o save() do formulário recalcularia (diárias sem valor): fica
        # como está, e a trilha registra só o campo pedido.
        type(o).objects.filter(pk=o.pk).update(diarias_quantidade_servidores=None)
        with self.captureOnCommitCallbacks(execute=True):
            self.patch(o, 'motivo', {'motivo': 'Diligência'})
        registro = RegistroAuditoria.objects.filter(modelo='viagens_oficios.oficio', objeto_id=str(o.pk), origem='editor').latest('criado_em')
        self.assertEqual(set(registro.alteracoes) - {'atualizado_em'}, {'motivo'})
        o.refresh_from_db()
        self.assertIsNone(o.diarias_quantidade_servidores)

    def test_regra_composta_do_formulario_vale_no_editor(self):
        o = self.criar()
        r = self.patch(o, 'custeio', {'custeio': 'OUTRA_INSTITUICAO', 'custeio_observacao': ''})
        self.assertEqual(r.status_code, 400)
        self.assertIn('custeio_observacao', r.json()['erros'])
        r = self.patch(o, 'custeio', {'custeio': 'OUTRA_INSTITUICAO', 'custeio_observacao': 'Ministério Público'})
        self.assertEqual(r.status_code, 200, r.content)
        o.refresh_from_db()
        self.assertEqual((o.custeio, o.custeio_observacao), ('OUTRA_INSTITUICAO', 'Ministério Público'))

    def test_so_o_registro_passa(self):
        o = self.criar()
        self.assertEqual(self.client.get(self.url(o, 'status')).status_code, 404)
        self.assertEqual(self.patch(o, 'status', {'status': 'ARQUIVADO'}).status_code, 404)
        # Chave válida, mas valor de outro campo escondido no corpo: 400.
        self.assertEqual(self.patch(o, 'motivo', {'motivo': 'x', 'status': 'ARQUIVADO'}).status_code, 400)
        self.assertEqual(self.client.get(self.url(o, 'motivo', tipo='contrato')).status_code, 404)
        o.refresh_from_db()
        self.assertEqual(o.status, 'RASCUNHO')

    def test_viajantes_gravam_a_relacao_e_recalculam_as_diarias(self):
        o = self.criar()
        self.assertEqual(o.diarias_quantidade_servidores, 2)
        r = self.patch(o, 'servidores', {'servidores': [str(self.a.pk)]})
        self.assertEqual(r.status_code, 200, r.content)
        o.refresh_from_db()
        self.assertEqual(list(o.servidores.values_list('pk', flat=True)), [self.a.pk])
        self.assertEqual(o.diarias_quantidade_servidores, 1)
        # O termo de autorização só pode ir para quem viaja (regra do clean).
        self.assertEqual(list(o.servidores_termo_autorizacao.values_list('pk', flat=True)), [self.a.pk])

    def test_data_e_booleano(self):
        o = self.criar()
        self.assertEqual(self.patch(o, 'data_criacao', {'data_criacao': '2026-09-12'}).status_code, 200)
        self.assertEqual(self.patch(o, 'porte_transporte_armas', {'porte_transporte_armas': True}).status_code, 200)
        o.refresh_from_db()
        self.assertEqual(o.data_criacao, date(2026, 9, 12))
        self.assertTrue(o.porte_transporte_armas)
        self.assertEqual(self.patch(o, 'porte_transporte_armas', {'porte_transporte_armas': False}).status_code, 200)
        o.refresh_from_db()
        self.assertFalse(o.porte_transporte_armas)

    def test_corpo_invalido_e_400(self):
        o = self.criar()
        r = self.client.patch(self.url(o, 'motivo'), data='{nada', content_type='application/json')
        self.assertEqual(r.status_code, 400)
        r = self.client.patch(self.url(o, 'motivo'), data=json.dumps({'valores': {'motivo': ['lista']}}), content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_quem_nao_opera_nao_edita_e_a_folha_nao_marca(self):
        o = self.criar()
        leitor = get_user_model().objects.create_user(username='leitor', deve_trocar_senha=False)
        leitor.setores.add(self.setor)
        self.client.force_login(leitor)
        self.assertEqual(self.client.get(self.url(o, 'motivo')).status_code, 403)
        self.assertEqual(self.patch(o, 'motivo', {'motivo': 'x'}).status_code, 403)
        folha = self.client.get(reverse('viagens_oficios:documento_folha', args=[o.pk])).content.decode()
        self.assertNotIn('data-doc-campo', folha)
        pagina = self.client.get(reverse('viagens_oficios:documento', args=[o.pk]))
        self.assertNotContains(pagina, 'data-de-editor')

    def test_operador_ve_a_folha_marcada_e_o_painel(self):
        o = self.criar()
        folha = self.client.get(reverse('viagens_oficios:documento_folha', args=[o.pk])).content.decode()
        for chave in ['motivo', 'protocolo', 'data_criacao', 'servidores', 'custeio', 'porte_transporte_armas']:
            self.assertIn(f'data-doc-campo="{chave}"', folha)
        self.assertNotIn('data-doc-campo="roteiro"', folha)  # marcado no template, fora do registro
        pagina = self.client.get(reverse('viagens_oficios:documento', args=[o.pk]))
        self.assertContains(pagina, 'data-de-editor')
        self.assertContains(pagina, 'data-de-abrir="motivo"')

    def test_oficio_cancelado_nao_se_edita(self):
        o = self.criar()
        o.cancelado = True
        o.save(update_fields=['cancelado', 'atualizado_em'])
        self.assertEqual(self.patch(o, 'motivo', {'motivo': 'x'}).status_code, 403)
