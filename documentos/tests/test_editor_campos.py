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
from documentos.services.types import DocumentoTipo
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
        # O histórico mora no editor do documento, embutido no fim do formulário,
        # em linguagem do documento: rótulo, de → para e "Voltar a este valor" (m116).
        r = self.client.get(reverse('documentos:editor_embutido', args=['oficio', o.pk]) + '?modo=campos')
        self.assertContains(r, 'Editor documental')
        self.assertContains(r, 'Motivo da viagem:')
        self.assertContains(r, '<s>Missão F4</s> → <b>Diligência</b>')
        self.assertContains(r, 'Criação do texto do modelo')
        self.assertContains(r, 'Declaração do cartão corporativo:')
        self.assertContains(r, 'Formulário')  # a criação do ofício, pela tela
        self.assertContains(r, 'data-de-voltar=')
        self.assertContains(r, '&quot;valores&quot;: {&quot;motivo&quot;: &quot;Missão F4&quot;}')
        self.assertNotContains(r, 'Editor documental · motivo')

    def test_historico_agrupa_a_mesma_digitacao_e_quem_so_le_nao_tem_voltar(self):
        from documentos.editor.historico import historico_legivel
        from documentos.editor.vinculos import vinculo_do_tipo
        with self.captureOnCommitCallbacks(execute=True):
            o = self.criar()
            for texto in ('Dil', 'Dilig', 'Diligência'):
                self.patch(o, 'motivo', {'motivo': texto})
        vinculo = vinculo_do_tipo('oficio')
        entradas = historico_legivel(vinculo, vinculo.historico(o), pode_editar=True)
        motivo = entradas[0]
        self.assertEqual(motivo['agrupados'], 3)
        self.assertEqual(motivo['mudancas'][0]['rotulo'], 'Motivo da viagem')
        self.assertEqual((motivo['mudancas'][0]['antes'], motivo['mudancas'][0]['depois']), ('Missão F4', 'Diligência'))
        self.assertEqual(motivo['mudancas'][0]['voltar'], {'especie': 'campo', 'chave': 'motivo', 'origem': 'oficio', 'valores': {'motivo': 'Missão F4'}})
        # Sem permissão de editar, o botão não existe; a criação do ofício é uma entrada só.
        entradas = historico_legivel(vinculo, vinculo.historico(o), pode_editar=False)
        self.assertTrue(all(m['voltar'] is None for e in entradas for m in e['mudancas']))
        self.assertEqual(entradas[-1]['mudancas'][0]['rotulo'], 'Registro criado')

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
        pagina = self.client.get(reverse('documentos:editor_embutido', args=['oficio', o.pk]) + '?modo=campos')
        self.assertNotContains(pagina, 'data-de-editor')

    def test_operador_ve_a_folha_marcada_e_o_painel(self):
        o = self.criar()
        folha = self.client.get(reverse('viagens_oficios:documento_folha', args=[o.pk])).content.decode()
        for chave in ['motivo', 'protocolo', 'data_criacao', 'servidores', 'custeio', 'porte_transporte_armas']:
            self.assertIn(f'data-doc-campo="{chave}"', folha)
        self.assertIn('data-doc-campo="roteiro"', folha)  # o roteiro também: o balão leva ao editor de roteiros
        pagina = self.client.get(reverse('documentos:editor_embutido', args=['oficio', o.pk]) + '?modo=campos')
        self.assertContains(pagina, 'data-de-editor')
        self.assertContains(pagina, 'data-de-abrir="motivo"')

    def test_oficio_cancelado_nao_se_edita(self):
        o = self.criar()
        o.cancelado = True
        o.save(update_fields=['cancelado', 'atualizado_em'])
        self.assertEqual(self.patch(o, 'motivo', {'motivo': 'x'}).status_code, 403)

    def test_oficio_finalizado_ou_assinado_nao_se_edita_no_editor(self):
        from django.core.files.base import ContentFile
        from documentos.models import DocumentoArtefato, DocumentoAssinaturaVersao
        o = self.criar()
        o.status = o.STATUS_FINALIZADO
        o.save(update_fields=['status', 'atualizado_em'])
        self.assertEqual(self.patch(o, 'motivo', {'motivo': 'x'}).status_code, 403)
        folha = self.client.get(reverse('documentos:editor_folha', args=['oficio', o.pk])).content.decode()
        self.assertNotIn('data-doc-campo="motivo"', folha)
        o.status = o.STATUS_GERADO
        o.save(update_fields=['status', 'atualizado_em'])
        self.assertEqual(self.patch(o, 'motivo', {'motivo': 'De novo'}).status_code, 200)
        artefato = DocumentoArtefato.objects.create(tipo='oficio', formato='pdf', oficio=o, hash_sha256='0' * 64,
                                                    arquivo=ContentFile(b'%PDF-1.4', name='o.pdf'))
        DocumentoAssinaturaVersao.objects.create(artefato=artefato, arquivo=ContentFile(b'%PDF-1.4 a', name='a.pdf'), hash_sha256='1' * 64)
        self.assertEqual(self.patch(o, 'motivo', {'motivo': 'x'}).status_code, 403)


class FolhaNaRespostaTests(CenarioOficioMixin, TestCase):
    """A gravação já devolve a folha remontada, para o navegador trocar o
    conteúdo no lugar em vez de recarregar o iframe."""

    def url(self, oficio, chave, tipo='oficio'):
        return reverse('documentos:editor_campo', args=[tipo, oficio.pk, chave])

    def patch(self, oficio, chave, valores):
        oficio.refresh_from_db()
        corpo = {'valores': valores, 'versao': oficio.atualizado_em.isoformat()}
        return self.client.patch(self.url(oficio, chave), data=json.dumps(corpo), content_type='application/json')

    def test_gravar_campo_devolve_a_folha_com_o_texto_novo(self):
        o = self.criar()
        r = self.patch(o, 'motivo', {'motivo': 'Escolta de autoridade em evento'})
        self.assertEqual(r.status_code, 200)
        folha = r.json()['folha']
        # Sai como o domínio grava: o motivo vai para caixa de título.
        self.assertIn('Escolta de Autoridade em Evento', folha)
        # É a folha do modo editor: vem marcada para receber clique.
        self.assertIn('data-doc-campo="motivo"', folha)
        self.assertIn('POLÍCIA CIVIL DO PARANÁ', folha)

    def test_a_folha_da_resposta_e_a_mesma_da_rota_do_iframe(self):
        o = self.criar()
        da_gravacao = self.patch(o, 'motivo', {'motivo': 'Apoio a operação conjunta'}).json()['folha']
        da_rota = self.client.get(reverse('viagens_oficios:documento_folha', args=[o.pk])).content.decode()
        self.assertEqual(da_gravacao, da_rota)

    def test_ligar_quebra_de_pagina_tambem_devolve_a_folha(self):
        o = self.criar()
        url = reverse('documentos:editor_quebra', args=['oficio', o.pk, 'apos_equipe'])
        r = self.client.patch(url, data=json.dumps({'ativa': True}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['ativa'])
        self.assertIn('POLÍCIA CIVIL DO PARANÁ', r.json()['folha'])


class TrechoDigitavelTests(CenarioOficioMixin, TestCase):
    """O que é texto sai da folha como campo de digitação; o que é escolha,
    alternância ou busca em registros continua clicável."""

    def folha(self, oficio):
        return self.client.get(reverse('viagens_oficios:documento_folha', args=[oficio.pk])).content.decode()

    def test_texto_livre_sai_editavel_na_folha(self):
        folha = self.folha(self.criar())
        # Motivo: texto longo, aceita mais de uma linha.
        self.assertIn('data-doc-campo="motivo" data-doc-parte="motivo" data-doc-digitavel="varias"', folha)
        # Protocolo: texto de uma linha só.
        self.assertIn('data-doc-campo="protocolo" data-doc-parte="protocolo" data-doc-digitavel="uma"', folha)
        # Parágrafo do modelo também é texto puro.
        self.assertIn('data-doc-bloco="declaracao_cartao" data-doc-digitavel="varias"', folha)
        # Texto de uma parte só, de qualquer origem, se escreve na folha: além de
        # motivo, protocolo e dos parágrafos do modelo, nome/CPF de cada servidor
        # e o número da solicitação.
        self.assertIn('data-doc-campo="servidor_cpf" data-doc-parte="cpf" data-doc-digitavel="uma" data-doc-origem="servidor"', folha)
        self.assertNotIn('data-doc-campo="config_', folha)  # configuração é da gestão

    def test_escolha_alternancia_e_relacao_seguem_clicaveis(self):
        folha = self.folha(self.criar())
        for chave in ('custeio', 'servidores', 'porte_transporte_armas', 'data_criacao'):
            self.assertIn(f'data-doc-campo="{chave}" data-doc-origem="oficio" class="doc-editavel" tabindex="0"', folha)
            self.assertNotIn(f'data-doc-campo="{chave}" data-doc-parte=', folha)

    def test_a_folha_do_pdf_nao_recebe_nada_de_edicao(self):
        from documentos.services.document_context import contexto_do_oficio
        from documentos.services.pdf_renderer import renderizar_html

        o = self.criar()
        html = renderizar_html(DocumentoTipo.OFICIO, contexto_do_oficio(o, modo='pdf'), modo='pdf')
        for marca in ('contenteditable', 'data-doc-digitavel', 'data-doc-campo', 'data-doc-bloco'):
            self.assertNotIn(marca, html)


class RegistroDigitavelTests(TestCase):
    def test_so_uma_parte_de_texto_e_digitavel(self):
        from documentos.editor.campos import campos_do_tipo

        campos = campos_do_tipo(DocumentoTipo.OFICIO)
        self.assertTrue(campos['motivo'].digitavel)
        self.assertTrue(campos['protocolo'].digitavel)
        # Escolha, booleano e data não se digitam.
        self.assertFalse(campos['custeio'].digitavel)
        self.assertFalse(campos['servidores'].digitavel)
        self.assertFalse(campos['porte_transporte_armas'].digitavel)
        self.assertFalse(campos['data_criacao'].digitavel)


class PendenciasNavegaveisTests(CenarioOficioMixin, TestCase):
    """Cada pendência leva ao trecho que a resolve; as lacunas da folha são
    marcadas para o atalho "Próximo campo vazio" (m117)."""

    def test_pendencia_vira_botao_para_o_campo_e_lacuna_e_marcada(self):
        from documentos.editor.vinculos import vinculo_do_tipo
        o = self.criar()
        type(o).objects.filter(pk=o.pk).update(motivo='', protocolo='')
        o.refresh_from_db()
        navegaveis = vinculo_do_tipo('oficio').pendencias_navegaveis(o)
        self.assertEqual([(p['texto'], p['campo'], p['origem']) for p in navegaveis],
                         [('Informe o protocolo.', 'protocolo', 'oficio'), ('Informe o motivo.', 'motivo', 'oficio')])
        r = self.client.get(reverse('documentos:editor_embutido', args=['oficio', o.pk]) + '?modo=campos')
        self.assertContains(r, 'class="dc-aviso__ir" data-de-abrir="motivo" data-de-origem="oficio"')
        self.assertContains(r, 'data-de-proximo-vazio')
        # Sem quem assina, a folha traz a lacuna marcada para a navegação.
        self.cfg.assinaturas.all().delete()
        folha = self.client.get(reverse('documentos:editor_folha', args=['oficio', o.pk])).content.decode()
        self.assertIn('data-doc-vazio="quem assina"', folha)


class TextosProntosTests(CenarioOficioMixin, TestCase):
    """Os modelos de texto do sistema dentro do editor (m118)."""

    def test_endpoint_lista_os_modelos_do_campo_com_marcadores_trocados(self):
        from viagens_oficios.models import ModeloMotivoOficio
        o = self.criar()
        ModeloMotivoOficio.objects.create(nome="COBERTURA", texto="Cobertura em {destino}, {periodo}.")
        r = self.client.get(reverse("documentos:editor_textos", args=["oficio", o.pk, "motivo"]))
        self.assertEqual(r.status_code, 200, r.content)
        textos = r.json()["textos"]
        self.assertEqual(textos[0]["nome"], "COBERTURA")
        self.assertEqual(textos[0]["texto"], "Cobertura em LONDRINA/PR, 10/09/2026 a 11/09/2026.")
        # Campo sem modelos: lista vazia; campo fora do registro: 404.
        self.assertEqual(self.client.get(reverse("documentos:editor_textos", args=["oficio", o.pk, "protocolo"])).json()["textos"], [])
        self.assertEqual(self.client.get(reverse("documentos:editor_textos", args=["oficio", o.pk, "nada"])).status_code, 404)
        r = self.client.get(reverse("documentos:editor_embutido", args=["oficio", o.pk]) + "?modo=campos")
        self.assertContains(r, 'data-de-textos-campos="motivo"')
        self.assertContains(r, "Inserir texto pronto")

    def test_sem_modelos_o_menu_nao_aparece(self):
        o = self.criar()
        r = self.client.get(reverse("documentos:editor_embutido", args=["oficio", o.pk]) + "?modo=campos")
        self.assertContains(r, 'data-de-textos-campos=""')
        self.assertNotContains(r, "Inserir texto pronto")
