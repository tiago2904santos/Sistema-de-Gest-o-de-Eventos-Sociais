from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
from datetime import date
from datetime import datetime
from decimal import Decimal
import json
import tempfile
from unittest import mock
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from .test_helpers import PrestacaoTestCase as TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from viagens_cadastros.models import Cargo
from viagens_cadastros.models import ConfiguracaoSistema
from viagens_cadastros.models import Servidor
from viagens_cadastros.models import Unidade
from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context
from viagens_oficios.models import Oficio
from viagens_prestacoes.forms import RelatorioTecnicoForm
from viagens_prestacoes.models import DiarioBordo
from viagens_prestacoes.models import PrestacaoContas
from viagens_prestacoes.models import PrestacaoDocumentoAnexo
from viagens_prestacoes.models import RelatorioTecnico
from viagens_prestacoes.presenters import apresentar_prestacao_servidor_card
from viagens_prestacoes.services import build_relatorio_tecnico_context
from viagens_prestacoes.services import descricao_ajustes_prestacao
from viagens_prestacoes.services import garantir_campos_padrao_relatorio_tecnico
from viagens_prestacoes.test_helpers import imagem_bytes
from viagens_roteiros.models import Roteiro
from viagens_roteiros.models import RoteiroTrecho

class PrestacaoContasSignalsTests(TestCase):

    def setUp(self):
        self.cargo = Cargo.objects.create(nome='Agente')
        self.servidor_a = Servidor.objects.create(nome='Servidor A', cargo=self.cargo, cpf='11122233344')
        self.servidor_b = Servidor.objects.create(nome='Servidor B', cargo=self.cargo, cpf='55566677788')

    def test_cria_prestacao_para_cada_servidor_adicionado_ao_oficio(self):
        oficio = Oficio.objects.create(numero=1, ano=2026, protocolo='123456789', status=Oficio.STATUS_RASCUNHO)
        oficio.servidores.add(self.servidor_a, self.servidor_b)
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        self.assertEqual(set(prestacao.servidores_prestacao.values_list('servidor_id', flat=True)), {self.servidor_a.pk, self.servidor_b.pk})

    def test_remover_servidor_do_oficio_remove_da_prestacao(self):
        """Servidor retirado do ofício não deve continuar na prestação.

        Regressão: o wizard semeia a equipe do ofício anterior do evento; se o
        usuário troca os servidores, os semeados não podem sobrar na prestação
        (era o que misturava equipes entre ofícios do mesmo evento).
        """
        oficio = Oficio.objects.create(numero=3, ano=2026, protocolo='111222333', status=Oficio.STATUS_RASCUNHO)
        oficio.servidores.add(self.servidor_a, self.servidor_b)
        oficio.servidores.remove(self.servidor_a)
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        self.assertEqual(set(prestacao.servidores_prestacao.values_list('servidor_id', flat=True)), {self.servidor_b.pk})

    def test_set_servidores_reconcilia_equipe_da_prestacao(self):
        """``.set()`` (usado pelo ModelForm) deve deixar a prestação idêntica à equipe."""
        oficio = Oficio.objects.create(numero=4, ano=2026, protocolo='444555666', status=Oficio.STATUS_RASCUNHO)
        oficio.servidores.add(self.servidor_a, self.servidor_b)
        oficio.servidores.set([self.servidor_b])
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        self.assertEqual(set(prestacao.servidores_prestacao.values_list('servidor_id', flat=True)), {self.servidor_b.pk})

class RelatorioTecnicoDiariaTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester_prestacao', password='123456')
        self.client.force_login(self.user)
        autorizar_viagens(self.user)
        self.cargo = Cargo.objects.create(nome='Agente')
        self.servidor_a = Servidor.objects.create(nome='Servidor A', cargo=self.cargo, cpf='11122233344')
        self.servidor_b = Servidor.objects.create(nome='Servidor B', cargo=self.cargo, cpf='55566677788')

    def test_diaria_inicial_e_valor_por_servidor_da_prestacao(self):
        """`NOVO-20260826-021706-c02af444709b`: esperava R$100,00 e congelava o defeito.

        `Roteiro.valor_diarias` é o valor de UM servidor — quem grava recalcula
        com `quantidade_servidores=1` antes de persistir, e é por isso que
        `Oficio.diarias_para_servidores` multiplica pelo efetivo. Este teste
        afirmava que dois servidores partiam a diária ao meio no RT; era a
        divisão indevida, não a regra. Com R$200,00 no roteiro, cada servidor
        saca R$200,00, e o ofício autoriza R$400,00 para a dupla.
        """
        roteiro = Roteiro.objects.create(valor_diarias=Decimal('200.00'))
        oficio = Oficio.objects.create(numero=1, ano=2026, protocolo='123456789', roteiro=roteiro)
        oficio.servidores.add(self.servidor_a, self.servidor_b)
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        ps = prestacao.servidores_prestacao.get(servidor=self.servidor_a)
        response = self.client.get(reverse('viagens_prestacoes:rt_servidor', args=[ps.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="R$200,00"')
        relatorio = RelatorioTecnico.objects.get(prestacao=prestacao)
        self.assertEqual(relatorio.diaria, 'R$200,00')
        self.assertEqual(relatorio.translado, 'Não houve')
        self.assertEqual(relatorio.combustivel, 'Cartão Prime')
        self.assertEqual(relatorio.passagem, 'Não houve')

    def test_link_de_modelos_preserva_retorno_para_o_relatorio(self):
        oficio = Oficio.objects.create(numero=2, ano=2026, protocolo='987654321')
        oficio.servidores.add(self.servidor_a)
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        ps = prestacao.servidores_prestacao.get(servidor=self.servidor_a)
        rt_url = reverse('viagens_prestacoes:rt_servidor', args=[ps.pk])
        response = self.client.get(rt_url)
        manage_url = response.context['campos_modelo'][0]['manage_url']
        self.assertIn('next=%2Fviagens%2Fprestacoes%2Fservidor-prestacao%2F', manage_url)
        self.assertIn(f'%2F{ps.pk}%2Frt%2F', manage_url)
        self.assertTrue(manage_url.endswith('#grupo-motivo'))

    def test_rodape_do_rt_nao_exibe_botao_salvar_texto(self):
        oficio = Oficio.objects.create(numero=3, ano=2026, protocolo='123123123')
        oficio.servidores.add(self.servidor_a)
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        ps = prestacao.servidores_prestacao.get(servidor=self.servidor_a)
        response = self.client.get(reverse('viagens_prestacoes:rt_servidor', args=[ps.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Salvar texto')
        self.assertContains(response, 'Salvar e continuar')

    def test_salvar_oficio_sincroniza_prestacoes_para_equipe_existente(self):
        oficio = Oficio.objects.create(numero=2, ano=2026, protocolo='987654321', status=Oficio.STATUS_RASCUNHO)
        oficio.servidores.add(self.servidor_a, self.servidor_b)
        PrestacaoContas.objects.filter(oficio=oficio).delete()
        oficio.assunto = 'Atualizacao'
        oficio.save(update_fields=['assunto', 'atualizado_em'])
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        self.assertEqual(set(prestacao.servidores_prestacao.values_list('servidor_id', flat=True)), {self.servidor_a.pk, self.servidor_b.pk})

class PrestacaoServidorDiariaOverrideTests(TestCase):
    """Sobrescrita da diária de um único servidor (ex.: saque em vez de transferência)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester_diaria_override', password='123456')
        self.client.force_login(self.user)
        autorizar_viagens(self.user)
        self.cargo = Cargo.objects.create(nome='Agente')
        self.servidor_a = Servidor.objects.create(nome='Servidor A', cargo=self.cargo, cpf='11122233344')
        self.servidor_b = Servidor.objects.create(nome='Servidor B', cargo=self.cargo, cpf='55566677788')
        self.oficio = Oficio.objects.create(numero=9, ano=2026, protocolo='123456789')
        self.oficio.servidores.add(self.servidor_a, self.servidor_b)
        self.prestacao = PrestacaoContas.objects.get(oficio=self.oficio)
        self.relatorio = RelatorioTecnico.objects.create(prestacao=self.prestacao, diaria='R$100,00', translado='Não houve', combustivel='Cartão Prime', passagem='Não houve')
        self.ps_a = self.prestacao.servidores_prestacao.get(servidor=self.servidor_a)
        self.ps_b = self.prestacao.servidores_prestacao.get(servidor=self.servidor_b)

    def test_contexto_usa_valor_padrao_quando_nao_ha_override(self):
        contexto = build_relatorio_tecnico_context(self.relatorio, self.ps_a)
        self.assertEqual(contexto['diaria'], 'R$100,00')

    def test_contexto_usa_override_apenas_do_servidor_ajustado(self):
        self.ps_b.diaria_valor_override = Decimal('80.00')
        self.ps_b.save(update_fields=['diaria_valor_override'])
        self.assertEqual(build_relatorio_tecnico_context(self.relatorio, self.ps_a)['diaria'], 'R$100,00')
        self.assertEqual(build_relatorio_tecnico_context(self.relatorio, self.ps_b)['diaria'], 'R$80,00')

    def test_rt_criar_get_mostra_selo_e_campo_de_override(self):
        self.ps_b.diaria_valor_override = Decimal('80.00')
        self.ps_b.save(update_fields=['diaria_valor_override'])
        response = self.client.get(reverse('viagens_prestacoes:rt_servidor', args=[self.ps_b.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Diária ajustada')
        self.assertContains(response, f'ps-{self.ps_b.pk}-diaria_valor_override')
        self.assertContains(response, 'Diária recebida por este servidor')

    def test_rt_autosave_salva_override_de_um_servidor_sem_afetar_o_outro(self):
        field_name = f'ps-{self.ps_b.pk}-diaria_valor_override'
        payload = {'object_id': str(self.relatorio.pk), 'form_id': '', 'model': 'relatorio_tecnico', 'dirty_fields': [field_name], 'fields': {field_name: 'R$80,00 (saque)'}, 'snapshots': {}}
        response = self.client.post(reverse('viagens_prestacoes:rt_autosave', args=[self.relatorio.pk]), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.ps_a.refresh_from_db()
        self.ps_b.refresh_from_db()
        self.relatorio.refresh_from_db()
        self.assertEqual(self.ps_b.diaria_valor_override, Decimal('80.00'))
        self.assertEqual(self.ps_b.diaria_valor_override_observacao, '(saque)')
        self.assertIsNone(self.ps_a.diaria_valor_override)
        self.assertEqual(self.relatorio.diaria, 'R$100,00')

    def test_rt_criar_post_salva_override_sem_js(self):
        data = {'diaria': 'R$100,00', 'translado': 'Não houve', 'combustivel': 'Cartão Prime', 'passagem': 'Não houve', 'motivo': '', 'atividade': '', 'conclusao': '', 'medidas': '', 'info_complementares': '', f'ps-{self.ps_b.pk}-diaria_valor_override': 'R$80,00'}
        response = self.client.post(reverse('viagens_prestacoes:rt_servidor', args=[self.ps_b.pk]), data=data)
        self.assertEqual(response.status_code, 302)
        self.ps_a.refresh_from_db()
        self.ps_b.refresh_from_db()
        self.assertEqual(self.ps_b.diaria_valor_override, Decimal('80.00'))
        self.assertIsNone(self.ps_a.diaria_valor_override)

    def test_autosave_salva_periodo_de_liberacao_e_saque(self):
        liberacao_name = f'ps-{self.ps_a.pk}-data_liberacao_diarias'
        prazo_name = f'ps-{self.ps_a.pk}-prazo_limite_saque'
        payload = {'object_id': str(self.ps_a.pk), 'form_id': '', 'model': 'prestacao_servidor', 'dirty_fields': [liberacao_name, prazo_name], 'fields': {liberacao_name: '2026-07-16', prazo_name: '2026-07-23'}, 'snapshots': {}}
        response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_solicitacao_autosave', args=[self.ps_a.pk]), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.ps_a.refresh_from_db()
        self.assertEqual(self.ps_a.data_liberacao_diarias, date(2026, 7, 16))
        self.assertEqual(self.ps_a.prazo_limite_saque, date(2026, 7, 23))

    def test_post_sem_js_salva_periodo_de_liberacao_e_saque(self):
        response = self.client.post(reverse('viagens_prestacoes:index'), data={'action': 'save_solicitacoes', f'ps-{self.ps_a.pk}-data_liberacao_diarias': '2026-07-16', f'ps-{self.ps_a.pk}-prazo_limite_saque': '2026-07-23'})
        self.assertEqual(response.status_code, 302)
        self.ps_a.refresh_from_db()
        self.assertEqual(self.ps_a.data_liberacao_diarias, date(2026, 7, 16))
        self.assertEqual(self.ps_a.prazo_limite_saque, date(2026, 7, 23))

    def test_card_oferece_pdfs_individuais_e_consolidado_no_menu(self):
        diario = DiarioBordo.objects.create(prestacao=self.prestacao)
        card = apresentar_prestacao_servidor_card(self.ps_a)
        servidor = card['servidores'][0]
        self.assertEqual(servidor['rt_download_url'], reverse('viagens_prestacoes:rt_download_servidor_formato', args=[self.ps_a.pk, 'pdf']))
        self.assertEqual(servidor['diario_pdf_url'], reverse('viagens_prestacoes:diario_download_formato', args=[diario.pk, 'pdf']))
        self.assertEqual(servidor['pacote_url'], reverse('viagens_prestacoes:consolidado_download', args=[self.ps_a.pk]))

    def test_card_oferece_seletor_consolidado_de_downloads_no_rodape(self):
        card = apresentar_prestacao_servidor_card(self.ps_a)
        self.assertEqual(card['downloads_url'], reverse('viagens_prestacoes:prestacao_downloads', args=[self.ps_a.pk]))
        response = self.client.get(reverse('viagens_prestacoes:index'))
        self.assertContains(response, 'Documentos e downloads')
        self.assertContains(response, reverse('viagens_prestacoes:consolidado_servidor', args=[self.ps_a.pk]))

    def test_downloads_lista_origens_e_disponibilidade_por_documento(self):
        DiarioBordo.objects.create(prestacao=self.prestacao)
        PrestacaoDocumentoAnexo.objects.create(prestacao=self.prestacao, servidor_prestacao=self.ps_a, tipo=PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO, arquivo=SimpleUploadedFile('rt.pdf', pdf_minimo(), content_type='application/pdf'), nome_original='rt.pdf')
        response = self.client.get(reverse('viagens_prestacoes:prestacao_downloads', args=[self.ps_a.pk]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['sempre_escolher'])
        self.assertEqual([origem['value'] for origem in payload['origens']], ['original', 'assinado'])
        itens = {item['id']: item for item in payload['itens']}
        self.assertEqual(set(itens['oficio']['versoes']['original']), {'pdf', 'docx'})
        self.assertEqual(set(itens['diario']['versoes']['original']), {'pdf'})
        self.assertEqual(set(itens['rt']['versoes']['original']), {'pdf', 'docx'})
        self.assertEqual(set(itens['rt']['versoes']['assinado']), {'pdf'})
        self.assertNotIn('comprovante', itens)

    @mock.patch('viagens_prestacoes.download_views.compilar_download', return_value=b'pacote')
    def test_download_compilado_recebe_somente_itens_marcados(self, compilar):
        response = self.client.get(reverse('viagens_prestacoes:prestacao_download_compilado', args=[self.ps_a.pk]), {'formato': 'docx', 'origem': 'original', 'itens': 'oficio,rt,invalido'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'pacote')
        compilar.assert_called_once_with(mock.ANY, origem='original', formato='docx', escolhidos=['oficio', 'rt'])

    def test_card_expoe_quantidade_persistida_de_diarias(self):
        roteiro = Roteiro.objects.create(resumo_diarias='6 x 100% + 1 x 15%')
        self.oficio.roteiro = roteiro
        self.oficio.save(update_fields=['roteiro', 'atualizado_em'])
        self.ps_a.refresh_from_db()
        card = apresentar_prestacao_servidor_card(self.ps_a)
        self.assertEqual(card['resumo_diarias_display'], '6 x 100% + 1 x 15%')

    def test_lista_cria_um_card_por_servidor_do_mesmo_oficio(self):
        response = self.client.get(reverse('viagens_prestacoes:index'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['cards']), 2)
        self.assertEqual({card['ps_pk'] for card in response.context['cards']}, {self.ps_a.pk, self.ps_b.pk})

    def test_arquivar_um_servidor_nao_arquiva_o_outro(self):
        response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_arquivar', args=[self.ps_a.pk]))
        self.assertEqual(response.status_code, 302)
        self.ps_a.refresh_from_db()
        self.ps_b.refresh_from_db()
        self.assertTrue(self.ps_a.arquivada)
        self.assertFalse(self.ps_b.arquivada)

class PrestacaoAssinadoUploadTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester_assinado_upload', password='123456')
        self.client.force_login(self.user)
        autorizar_viagens(self.user)
        cargo = Cargo.objects.create(nome='Agente')
        self.motorista = Servidor.objects.create(nome='Motorista', cargo=cargo, cpf='11122233344')
        self.servidor = Servidor.objects.create(nome='Servidor', cargo=cargo, cpf='55566677788')
        self.oficio = Oficio.objects.create(numero=18, ano=2026, protocolo='123456789', motorista=self.motorista)
        self.oficio.servidores.add(self.motorista, self.servidor)
        self.prestacao = PrestacaoContas.objects.get(oficio=self.oficio)
        self.ps_motorista = self.prestacao.servidores_prestacao.get(servidor=self.motorista)
        self.ps_servidor = self.prestacao.servidores_prestacao.get(servidor=self.servidor)

    def test_anexa_e_substitui_despacho_assinado(self):
        url = reverse('viagens_prestacoes:prestacao_despacho_assinado_anexar', args=[self.prestacao.pk])
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            for nome in ('despacho-1.pdf', 'despacho-2.pdf'):
                response = self.client.post(url, data={'arquivo': SimpleUploadedFile(nome, pdf_minimo(), content_type='application/pdf'), 'next': reverse('viagens_prestacoes:index')})
                self.assertEqual(response.status_code, 302)
            anexos = PrestacaoDocumentoAnexo.objects.filter(prestacao=self.prestacao, servidor_prestacao=None, tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO)
            self.assertEqual(anexos.count(), 1)
            self.assertEqual(anexos.get().nome_original, 'despacho-2.pdf')

    def test_diario_assinado_pode_ser_anexado_por_qualquer_servidor_e_e_compartilhado(self):
        tipo = PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_assinado_anexar', args=[self.ps_servidor.pk, tipo]), data={'arquivo': SimpleUploadedFile('diario-servidor.pdf', pdf_minimo(), content_type='application/pdf')})
            self.assertEqual(response.status_code, 302)
            response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_assinado_anexar', args=[self.ps_motorista.pk, tipo]), data={'arquivo': SimpleUploadedFile('diario-motorista.pdf', pdf_minimo(), content_type='application/pdf')})
            self.assertEqual(response.status_code, 302)
            anexos = PrestacaoDocumentoAnexo.objects.filter(prestacao=self.prestacao, servidor_prestacao=None, tipo=tipo)
            self.assertEqual(anexos.count(), 1)
            self.assertEqual(anexos.get().nome_original, 'diario-motorista.pdf')
            lista = self.client.get(reverse('viagens_prestacoes:index'))
            diarios = [kind for card in lista.context['cards'] for kind in json.loads(card['attach_kinds_json']) if kind['key'] == 'diario']
            self.assertEqual(len(diarios), 2)
            self.assertEqual([k['current_name'] for k in diarios], ['diario-motorista.pdf', 'diario-motorista.pdf'])

    def test_rejeita_formato_de_documento_nao_suportado(self):
        response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_assinado_anexar', args=[self.ps_servidor.pk, PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO]), data={'arquivo': SimpleUploadedFile('relatorio.txt', b'arquivo invalido', content_type='text/plain')})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PrestacaoDocumentoAnexo.objects.filter(prestacao=self.prestacao, servidor_prestacao=self.ps_servidor, tipo=PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO).exists())

    def test_aceita_png_jpg_e_jpeg(self):
        url = reverse('viagens_prestacoes:prestacao_servidor_assinado_anexar', args=[self.ps_servidor.pk, PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO])
        formatos = (('relatorio.png', imagem_bytes('PNG'), 'image/png'), ('relatorio.jpg', imagem_bytes('JPEG'), 'image/jpeg'), ('relatorio.jpeg', imagem_bytes('JPEG'), 'image/jpeg'))
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            for nome, conteudo, content_type in formatos:
                with self.subTest(nome=nome):
                    response = self.client.post(url, data={'arquivo': SimpleUploadedFile(nome, conteudo, content_type=content_type)})
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(PrestacaoDocumentoAnexo.objects.filter(prestacao=self.prestacao, servidor_prestacao=self.ps_servidor, tipo=PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO, nome_original=nome).exists())

    def test_anexa_comprovante_e_preserva_reabertura_do_modal(self):
        tipo = PrestacaoDocumentoAnexo.TIPO_COMPROVANTE
        next_url = reverse('viagens_prestacoes:index') + f'#attach-signed=prestacao-servidor-{self.ps_servidor.pk}&kind=tertiary'
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_assinado_anexar', args=[self.ps_servidor.pk, tipo]), data={'arquivo': SimpleUploadedFile('comprovante.pdf', pdf_minimo(), content_type='application/pdf'), 'next': next_url})
        self.assertRedirects(response, next_url, fetch_redirect_response=False)
        self.assertTrue(PrestacaoDocumentoAnexo.objects.filter(prestacao=self.prestacao, servidor_prestacao=self.ps_servidor, tipo=tipo, nome_original='comprovante.pdf').exists())

    def test_upload_assinado_nao_segue_next_externo(self):
        response = self.client.post(reverse('viagens_prestacoes:prestacao_despacho_assinado_anexar', args=[self.prestacao.pk]), {'next': 'https://externo.invalido/coleta'})
        self.assertRedirects(response, reverse('viagens_prestacoes:index'), fetch_redirect_response=False)

    def test_lista_oferece_documentos_por_servidor(self):
        response = self.client.get(reverse('viagens_prestacoes:index'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['cards']), 2)
        for card in response.context['cards']:
            ps_pk = card['servidores'][0]['ps_pk']
            documentos = self.client.get(reverse('viagens_prestacoes:documentos_servidor', args=[ps_pk]))
            self.assertEqual(len(documentos.context['uploads']), 5)
            self.assertContains(documentos, 'type="file"', count=5)
            self.assertContains(response, reverse('viagens_prestacoes:consolidado_servidor', args=[ps_pk]))

class RelatorioTecnicoDocumentoTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester_rt_doc', password='123456')
        self.client.force_login(self.user)
        autorizar_viagens(self.user)
        self.cargo = Cargo.objects.create(nome='Agente')
        self.servidor = Servidor.objects.create(nome='Servidor RT', cargo=self.cargo, cpf='11122233344')
        self.oficio = Oficio.objects.create(numero=7, ano=2026, protocolo='123456789')
        self.oficio.servidores.add(self.servidor)
        self.prestacao = PrestacaoContas.objects.get(oficio=self.oficio)
        self.ps = self.prestacao.servidores_prestacao.get(servidor=self.servidor)
        self.relatorio = RelatorioTecnico.objects.create(prestacao=self.prestacao, diaria='R$100,00', translado='Não houve', combustivel='Cartão Prime', passagem='Não houve', atividade='Atividade')

    def test_contexto_preenche_cabecalho_e_rodape_do_template(self):
        cfg = ConfiguracaoSistema.get_singleton()
        cfg.unidade = Unidade.objects.create(nome='UNIDADE TESTE')
        cfg.logradouro = 'RUA CENTRAL'
        cfg.numero = '123'
        cfg.bairro = 'CENTRO'
        cfg.cidade_endereco = 'CURITIBA'
        cfg.uf = 'PR'
        cfg.cep = '80000000'
        cfg.telefone = '4133334444'
        cfg.email = 'TESTE@PC.PR.GOV.BR'
        cfg.save()
        contexto = build_relatorio_tecnico_context(self.relatorio, self.ps)
        self.assertEqual(contexto['unidade_cabecalho'], 'UNIDADE TESTE')
        self.assertEqual(contexto['assunto_oficio'], 'Autorização')
        self.assertEqual(contexto['unidade_rodape'], 'Unidade Teste')
        self.assertIn('Rua Central', contexto['endereco'])
        self.assertIn('Curitiba/PR', contexto['endereco'])
        self.assertEqual(contexto['email'], 'teste@pc.pr.gov.br')

    def test_troca_por_motorista_do_mesmo_oficio_apenas_informa(self):
        motorista_original = Servidor.objects.create(nome='Motorista Original', cargo=self.cargo, cpf='22233344455')
        self.oficio.servidores.add(motorista_original)
        self.oficio.motorista = motorista_original
        self.oficio.save(update_fields=['motorista', 'atualizado_em'])
        self.prestacao.refresh_from_db()
        DiarioBordo.objects.create(prestacao=self.prestacao, motorista_modo=DiarioBordo.MOTORISTA_MODO_SERVIDOR, motorista_servidor=self.servidor)
        texto = descricao_ajustes_prestacao(self.prestacao)
        self.assertEqual(texto, 'Houve a troca do motorista Motorista Original para Servidor Rt.')

    def test_troca_de_viatura_apenas_informa(self):
        DiarioBordo.objects.create(prestacao=self.prestacao, viatura_modo=DiarioBordo.VIATURA_MODO_MANUAL, viatura_manual_modelo='Duster', viatura_manual_placa='AAA1234')
        texto = descricao_ajustes_prestacao(self.prestacao)
        self.assertEqual(texto, 'Houve a troca da viatura não informada para Duster — AAA-1234.')

    def test_motorista_de_outro_oficio_exige_justificativa(self):
        motorista_original = Servidor.objects.create(nome='Motorista Original', cargo=self.cargo, cpf='22233344455')
        self.oficio.servidores.add(motorista_original)
        self.oficio.motorista = motorista_original
        self.oficio.save(update_fields=['motorista', 'atualizado_em'])
        self.prestacao.refresh_from_db()
        DiarioBordo.objects.create(prestacao=self.prestacao, motorista_modo=DiarioBordo.MOTORISTA_MODO_OUTRO, motorista_manual_nome='Motorista Externo', motorista_manual_cpf='33344455566', motorista_oficio_referencia='20/2026')
        texto = descricao_ajustes_prestacao(self.prestacao)
        self.assertEqual(texto, 'Houve a troca do motorista Motorista Original para Motorista Externo. Justificativa: ')

    def test_texto_automatico_legado_sem_justificativa_digitada_e_corrigido(self):
        motorista_original = Servidor.objects.create(nome='Motorista Original', cargo=self.cargo, cpf='22233344455')
        self.oficio.servidores.add(motorista_original)
        self.oficio.motorista = motorista_original
        self.oficio.save(update_fields=['motorista', 'atualizado_em'])
        self.prestacao.refresh_from_db()
        DiarioBordo.objects.create(prestacao=self.prestacao, motorista_modo=DiarioBordo.MOTORISTA_MODO_SERVIDOR, motorista_servidor=self.servidor)
        self.relatorio.info_complementares = 'Houve a troca do motorista Motorista Original para Servidor Rt. Justificativa: '
        self.relatorio.save(update_fields=['info_complementares', 'atualizado_em'])
        atualizados = garantir_campos_padrao_relatorio_tecnico(self.relatorio)
        self.relatorio.refresh_from_db()
        self.assertIn('info_complementares', atualizados)
        self.assertEqual(self.relatorio.info_complementares, 'Houve a troca do motorista Motorista Original para Servidor Rt.')

    def test_justificativa_digitada_pelo_usuario_e_preservada(self):
        motorista_original = Servidor.objects.create(nome='Motorista Original', cargo=self.cargo, cpf='22233344455')
        self.oficio.servidores.add(motorista_original)
        self.oficio.motorista = motorista_original
        self.oficio.save(update_fields=['motorista', 'atualizado_em'])
        self.prestacao.refresh_from_db()
        DiarioBordo.objects.create(prestacao=self.prestacao, motorista_modo=DiarioBordo.MOTORISTA_MODO_SERVIDOR, motorista_servidor=self.servidor)
        texto_editado = 'Houve a troca do motorista Motorista Original para Servidor Rt. Justificativa: necessidade operacional.'
        self.relatorio.info_complementares = texto_editado
        self.relatorio.save(update_fields=['info_complementares', 'atualizado_em'])
        atualizados = garantir_campos_padrao_relatorio_tecnico(self.relatorio)
        self.relatorio.refresh_from_db()
        self.assertNotIn('info_complementares', atualizados)
        self.assertEqual(self.relatorio.info_complementares, texto_editado)

    def test_data_rt_nao_fica_antes_do_retorno(self):
        roteiro = Roteiro.objects.create(retorno_chegada_dt=timezone.make_aware(datetime(2026, 6, 19, 18, 0)))
        self.oficio.roteiro = roteiro
        self.oficio.save(update_fields=['roteiro', 'atualizado_em'])
        with mock.patch('viagens_prestacoes.services.timezone.localdate', return_value=date(2026, 6, 18)):
            contexto = build_relatorio_tecnico_context(self.relatorio, self.ps)
        self.assertEqual(contexto['data_atual_extenso'], '19 de junho de 2026')

    def test_data_rt_usa_hoje_dentro_de_tres_dias_uteis_apos_retorno(self):
        roteiro = Roteiro.objects.create(retorno_chegada_dt=timezone.make_aware(datetime(2026, 6, 19, 18, 0)))
        self.oficio.roteiro = roteiro
        self.oficio.save(update_fields=['roteiro', 'atualizado_em'])
        with mock.patch('viagens_prestacoes.services.timezone.localdate', return_value=date(2026, 6, 23)):
            contexto = build_relatorio_tecnico_context(self.relatorio, self.ps)
        self.assertEqual(contexto['data_atual_extenso'], '23 de junho de 2026')

    def test_data_rt_limita_ao_terceiro_dia_util_apos_retorno(self):
        roteiro = Roteiro.objects.create(retorno_chegada_dt=timezone.make_aware(datetime(2026, 6, 19, 18, 0)))
        self.oficio.roteiro = roteiro
        self.oficio.save(update_fields=['roteiro', 'atualizado_em'])
        with mock.patch('viagens_prestacoes.services.timezone.localdate', return_value=date(2026, 6, 30)):
            contexto = build_relatorio_tecnico_context(self.relatorio, self.ps)
        self.assertEqual(contexto['data_atual_extenso'], '24 de junho de 2026')

    def test_contexto_rt_usa_padrao_quando_campos_custeio_estao_em_branco(self):
        roteiro = Roteiro.objects.create(valor_diarias=Decimal('210.00'))
        self.oficio.roteiro = roteiro
        self.oficio.save(update_fields=['roteiro', 'atualizado_em'])
        RelatorioTecnico.objects.filter(pk=self.relatorio.pk).update(diaria='', translado='', combustivel='', passagem='')
        self.relatorio.refresh_from_db()
        contexto = build_relatorio_tecnico_context(self.relatorio, self.ps)
        self.assertEqual(contexto['diaria'], 'R$210,00')
        self.assertEqual(contexto['translado'], 'Não houve')
        self.assertEqual(contexto['combustivel'], 'Cartão Prime')
        self.assertEqual(contexto['passagem'], 'Não houve')

    @mock.patch('viagens_prestacoes.services.gerar_relatorio_tecnico_pdf', return_value=pdf_minimo())
    def test_download_pdf_do_rt(self, _mock_pdf):
        response = self.client.get(reverse('viagens_prestacoes:rt_download_servidor_formato', args=[self.ps.pk, 'pdf']))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('.pdf', response['Content-Disposition'])

    def test_download_rt_materializa_campos_padrao_antes_de_gerar(self):
        roteiro = Roteiro.objects.create(valor_diarias=Decimal('210.00'))
        self.oficio.roteiro = roteiro
        self.oficio.save(update_fields=['roteiro', 'atualizado_em'])
        RelatorioTecnico.objects.filter(pk=self.relatorio.pk).update(diaria='', translado='', combustivel='', passagem='')
        response = self.client.get(reverse('viagens_prestacoes:rt_download_servidor_formato', args=[self.ps.pk, 'docx']))
        self.assertEqual(response.status_code, 200)
        self.relatorio.refresh_from_db()
        self.assertEqual(self.relatorio.diaria, 'R$210,00')
        self.assertEqual(self.relatorio.translado, 'Não houve')
        self.assertEqual(self.relatorio.combustivel, 'Cartão Prime')
        self.assertEqual(self.relatorio.passagem, 'Não houve')

    def test_post_do_formulario_pode_solicitar_pdf(self):
        data = {'diaria': 'R$100,00', 'translado': 'Não houve', 'combustivel': 'Cartão Prime', 'passagem': 'Não houve', 'motivo': 'Motivo', 'atividade': 'Atividade', 'conclusao': 'Conclusão', 'medidas': 'Medidas', 'info_complementares': 'Info', 'action': 'download_pdf'}
        response = self.client.post(reverse('viagens_prestacoes:rt_servidor', args=[self.ps.pk]), data=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('viagens_prestacoes:rt_servidor', args=[self.ps.pk]))

    def test_formulario_rt_exibe_opcoes_especificas_para_campos_de_custeio(self):
        form = RelatorioTecnicoForm(instance=self.relatorio)
        self.assertEqual(list(form.fields['translado'].choices), [('Não houve', 'Não houve'), ('__outro__', 'Outro')])
        self.assertEqual(list(form.fields['combustivel'].choices), [('Cartão Prime', 'Cartão Prime'), ('__outro__', 'Outro')])
        self.assertEqual(list(form.fields['passagem'].choices), [('Não houve', 'Não houve'), ('__outro__', 'Outro')])

    def test_index_salva_numero_solicitacao_do_servidor(self):
        prefix = f'ps-{self.ps.pk}'
        response = self.client.post(reverse('viagens_prestacoes:index'), data={'action': 'save_solicitacoes', f'{prefix}-numero_solicitacao': 'SOL-123'})
        self.assertEqual(response.status_code, 302)
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, 'SOL-123')

    def test_autosave_salva_numero_solicitacao_prefixado_da_lista(self):
        prefix = f'ps-{self.ps.pk}'
        field_name = f'{prefix}-numero_solicitacao'
        payload = {'object_id': str(self.ps.pk), 'form_id': '', 'model': 'prestacao_servidor', 'dirty_fields': [field_name], 'fields': {field_name: 'SOL-AUTO'}, 'snapshots': {}}
        response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_solicitacao_autosave', args=[self.ps.pk]), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, 'SOL-AUTO')

    def test_documentos_salva_numero_e_anexos(self):
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            despacho_response = self.client.post(reverse('viagens_prestacoes:prestacao_arquivo_autosave', args=[self.prestacao.pk]), data={'despacho_arquivos': [SimpleUploadedFile('despacho.pdf', pdf_minimo(), content_type='application/pdf'), SimpleUploadedFile('despacho-extra.pdf', pdf_minimo(), content_type='application/pdf')]})
            comprovante_response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_arquivo_autosave', args=[self.ps.pk]), data={f'ps-{self.ps.pk}-numero_solicitacao': 'SOL-456', f'ps-{self.ps.pk}-comprovante_arquivos': [SimpleUploadedFile('comprovante.png', imagem_bytes('PNG'), content_type='image/png')]})
            self.assertEqual(despacho_response.status_code, 200)
            self.assertEqual(comprovante_response.status_code, 200)
            self.assertEqual(PrestacaoDocumentoAnexo.objects.filter(prestacao=self.prestacao, tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO).count(), 2)
            self.assertEqual(PrestacaoDocumentoAnexo.objects.filter(prestacao=self.prestacao, servidor_prestacao=self.ps, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE).count(), 1)

    def test_autosave_documentos_salva_numero_solicitacao(self):
        field_name = f'ps-{self.ps.pk}-numero_solicitacao'
        payload = {'object_id': str(self.ps.pk), 'form_id': '', 'model': 'prestacao_servidor', 'dirty_fields': [field_name], 'fields': {field_name: 'SOL-DOCS'}, 'snapshots': {}}
        response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_solicitacao_autosave', args=[self.ps.pk]), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, 'SOL-DOCS')

    def test_autosave_arquivo_documentos_salva_anexo(self):
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            response = self.client.post(reverse('viagens_prestacoes:prestacao_arquivo_autosave', args=[self.prestacao.pk]), data={'despacho_arquivos': [SimpleUploadedFile('despacho.pdf', pdf_minimo(), content_type='application/pdf'), SimpleUploadedFile('despacho-extra.pdf', pdf_minimo(), content_type='application/pdf')]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(PrestacaoDocumentoAnexo.objects.filter(prestacao=self.prestacao, tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO).count(), 2)

    def test_excluir_anexo_documentos(self):
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            anexo = PrestacaoDocumentoAnexo.objects.create(prestacao=self.prestacao, tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO, arquivo=SimpleUploadedFile('despacho.pdf', pdf_minimo(), content_type='application/pdf'), nome_original='despacho.pdf')
            response = self.client.post(reverse('viagens_prestacoes:prestacao_documento_delete', args=[self.prestacao.pk, anexo.pk]), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(response.status_code, 200)
            self.assertFalse(PrestacaoDocumentoAnexo.objects.filter(pk=anexo.pk).exists())

    def test_autosave_rt_salva_campos_do_relatorio(self):
        payload = {'object_id': str(self.relatorio.pk), 'form_id': '', 'model': 'relatorio_tecnico', 'dirty_fields': ['atividade', 'combustivel_outro'], 'fields': {'atividade': 'Atividade autosave', 'combustivel_outro': 'Combustível próprio'}, 'snapshots': {}}
        response = self.client.post(reverse('viagens_prestacoes:rt_autosave', args=[self.relatorio.pk]), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.relatorio.refresh_from_db()
        self.assertEqual(self.relatorio.atividade, 'Atividade autosave')
        self.assertEqual(self.relatorio.combustivel, 'Combustível próprio')

    def test_autosave_rt_nao_apaga_custeio_com_valor_vazio_de_tela_antiga(self):
        payload = {'object_id': str(self.relatorio.pk), 'form_id': '', 'model': 'relatorio_tecnico', 'dirty_fields': ['translado', 'combustivel', 'passagem'], 'fields': {'translado': '', 'combustivel': '', 'passagem': ''}, 'snapshots': {}}
        response = self.client.post(reverse('viagens_prestacoes:rt_autosave', args=[self.relatorio.pk]), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.relatorio.refresh_from_db()
        self.assertEqual(self.relatorio.translado, 'Não houve')
        self.assertEqual(self.relatorio.combustivel, 'Cartão Prime')
        self.assertEqual(self.relatorio.passagem, 'Não houve')

    def test_autosave_diario_salva_km_e_abastecimento(self):
        roteiro = Roteiro.objects.create()
        self.oficio.roteiro = roteiro
        self.oficio.save(update_fields=['roteiro', 'atualizado_em'])
        RoteiroTrecho.objects.create(roteiro=roteiro, sentido=RoteiroTrecho.Sentido.IDA, ordem=0)
        diario = DiarioBordo.objects.create(prestacao=self.prestacao)
        payload = {'object_id': str(diario.pk), 'form_id': '', 'model': 'diario_bordo', 'dirty_fields': ['form-0-km_inicial', 'form-0-abastecimento'], 'fields': {'form-0-km_inicial': '12.345', 'form-0-abastecimento': 'nao'}, 'snapshots': {}}
        response = self.client.post(reverse('viagens_prestacoes:diario_autosave', args=[diario.pk]), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        linha = diario.trechos.get()
        self.assertEqual(linha.km_inicial, 12345)
        self.assertFalse(linha.abastecimento)

    def test_numero_solicitacao_preenche_coluna_do_oficio(self):
        self.ps.numero_solicitacao = 'SOL-789'
        self.ps.save(update_fields=['numero_solicitacao', 'atualizado_em'])
        contexto = build_oficio_docxtpl_context(self.oficio)
        self.assertEqual(contexto['col_solicitacao'], 'SOL-789')

    def test_coluna_solicitacao_preserva_linha_vazia_para_outro_servidor(self):
        servidor_b = Servidor.objects.create(nome='Servidor ZZ', cargo=self.cargo, cpf='22233344455')
        self.oficio.servidores.add(servidor_b)
        self.ps.numero_solicitacao = 'SOL-789'
        self.ps.save(update_fields=['numero_solicitacao', 'atualizado_em'])
        contexto = build_oficio_docxtpl_context(self.oficio)
        self.assertEqual(contexto['col_solicitacao'], 'SOL-789\n\n\n')

    def test_consolidado_mostra_anexos_documentos_como_ok(self):
        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            PrestacaoDocumentoAnexo.objects.create(prestacao=self.prestacao, tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO, arquivo=SimpleUploadedFile('despacho.pdf', pdf_minimo(), content_type='application/pdf'), nome_original='despacho.pdf')
            PrestacaoDocumentoAnexo.objects.create(prestacao=self.prestacao, servidor_prestacao=self.ps, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE, arquivo=SimpleUploadedFile('comprovante-a.pdf', pdf_minimo(), content_type='application/pdf'), nome_original='comprovante-a.pdf')
            PrestacaoDocumentoAnexo.objects.create(prestacao=self.prestacao, servidor_prestacao=self.ps, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE, arquivo=SimpleUploadedFile('comprovante-b.pdf', pdf_minimo(), content_type='application/pdf'), nome_original='comprovante-b.pdf')
            response = self.client.get(reverse('viagens_prestacoes:consolidado_servidor', args=[self.ps.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Conferência')
        self.assertContains(response, 'Pacote final')
        servidor_ctx = response.context['servidores'][0]
        self.assertEqual(servidor_ctx['nome'], self.ps.servidor.nome)
        self.assertIn('download_url', servidor_ctx)

    @mock.patch('viagens_prestacoes.views.gerar_prestacao_consolidado_pdf', return_value=pdf_minimo())
    def test_download_pdf_consolidado(self, _mock_pdf):
        response = self.client.get(reverse('viagens_prestacoes:consolidado_download', args=[self.ps.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('.pdf', response['Content-Disposition'])

class PrestacaoAbasTests(TestCase):
    """Abas (não liberadas/liberadas/arquivados/finalizados) + ações arquivar/finalizar."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester_abas', password='123456')
        self.client.force_login(self.user)
        autorizar_viagens(self.user)
        self.cargo = Cargo.objects.create(nome='Agente')
        self.servidor = Servidor.objects.create(nome='Servidor Abas', cargo=self.cargo, cpf='11122233344')

    def _criar_prestacao(self, *, numero=1):
        """Cria um ofício (e, via signal, a prestação) com um servidor vinculado."""
        roteiro = Roteiro.objects.create(saida_dt=timezone.now())
        oficio = Oficio.objects.create(numero=numero, ano=2026, protocolo=f'1000000{numero}', roteiro=roteiro)
        oficio.servidores.add(self.servidor)
        return PrestacaoContas.objects.get(oficio=oficio).servidores_prestacao.get()

    def _pks(self, aba):
        from viagens_prestacoes import selectors
        return set(selectors.listar_prestacoes(aba=aba).values_list('pk', flat=True))

    def _liberar(self, ps):
        """Marca a data de liberação das diárias do (único) servidor da prestação."""
        ps.data_liberacao_diarias = timezone.localdate()
        ps.save(update_fields=['data_liberacao_diarias'])

    def test_prestacao_sem_data_liberacao_fica_em_nao_liberadas(self):
        from viagens_prestacoes import selectors
        ps = self._criar_prestacao(numero=1)
        self.assertIn(ps.pk, self._pks(selectors.ABA_NAO_LIBERADAS))
        self.assertNotIn(ps.pk, self._pks(selectors.ABA_LIBERADAS))

    def test_prestacao_com_servidor_liberado_move_para_liberadas(self):
        from viagens_prestacoes import selectors
        ps = self._criar_prestacao(numero=1)
        self._liberar(ps)
        self.assertIn(ps.pk, self._pks(selectors.ABA_LIBERADAS))
        self.assertNotIn(ps.pk, self._pks(selectors.ABA_NAO_LIBERADAS))

    def test_arquivar_move_para_aba_arquivados(self):
        from viagens_prestacoes import selectors
        ps = self._criar_prestacao()
        response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_arquivar', args=[ps.pk]), data={'next': '/prestacoes-contas/?aba=nao_liberadas'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/prestacoes-contas/?aba=nao_liberadas')
        ps.refresh_from_db()
        self.assertTrue(ps.arquivada)
        self.assertIsNotNone(ps.arquivada_em)
        self.assertNotIn(ps.pk, self._pks(selectors.ABA_NAO_LIBERADAS))
        self.assertIn(ps.pk, self._pks(selectors.ABA_ARQUIVADOS))
        self.client.post(reverse('viagens_prestacoes:prestacao_servidor_arquivar', args=[ps.pk]))
        ps.refresh_from_db()
        self.assertFalse(ps.arquivada)
        self.assertIsNone(ps.arquivada_em)
        self.assertIn(ps.pk, self._pks(selectors.ABA_NAO_LIBERADAS))

    def test_finalizar_tem_precedencia_sobre_arquivada(self):
        from viagens_prestacoes import selectors
        ps = self._criar_prestacao()
        ps.definir_arquivada(True)
        self.client.post(reverse('viagens_prestacoes:prestacao_servidor_finalizar', args=[ps.pk]))
        ps.refresh_from_db()
        self.assertTrue(ps.finalizada)
        self.assertIn(ps.pk, self._pks(selectors.ABA_FINALIZADOS))
        self.assertNotIn(ps.pk, self._pks(selectors.ABA_ARQUIVADOS))
        self.assertNotIn(ps.pk, self._pks(selectors.ABA_NAO_LIBERADAS))

    def test_contagem_por_aba(self):
        from viagens_prestacoes import selectors
        p_nao_lib = self._criar_prestacao(numero=1)
        p_lib = self._criar_prestacao(numero=2)
        self._liberar(p_lib)
        p_arq = self._criar_prestacao(numero=3)
        p_arq.definir_arquivada(True)
        p_fin = self._criar_prestacao(numero=4)
        p_fin.definir_finalizada(True)
        contagem = selectors.contar_por_aba()
        self.assertEqual(contagem[selectors.ABA_NAO_LIBERADAS], 1)
        self.assertEqual(contagem[selectors.ABA_LIBERADAS], 1)
        self.assertEqual(contagem[selectors.ABA_ARQUIVADOS], 1)
        self.assertEqual(contagem[selectors.ABA_FINALIZADOS], 1)
        self.assertIn(p_nao_lib.pk, self._pks(selectors.ABA_NAO_LIBERADAS))

class PrestacaoPorServidorFluxoTests(TestCase):
    """Cards e páginas individuais com dados compartilhados por ofício."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester_fluxo_ps', password='123456')
        self.client.force_login(self.user)
        autorizar_viagens(self.user)
        self.cargo = Cargo.objects.create(nome='Agente')
        self.servidor_a = Servidor.objects.create(nome='Servidor Um', cargo=self.cargo, cpf='11122233344')
        self.servidor_b = Servidor.objects.create(nome='Servidor Dois', cargo=self.cargo, cpf='55566677788')
        self.oficio = Oficio.objects.create(numero=21, ano=2026, protocolo='212121212')
        self.oficio.servidores.add(self.servidor_a, self.servidor_b)
        self.prestacao = PrestacaoContas.objects.get(oficio=self.oficio)
        self.ps_a = self.prestacao.servidores_prestacao.get(servidor=self.servidor_a)
        self.ps_b = self.prestacao.servidores_prestacao.get(servidor=self.servidor_b)

    def test_lista_gera_card_separado_por_servidor_agrupado_pelo_oficio(self):
        response = self.client.get(reverse('viagens_prestacoes:index'))
        self.assertEqual(response.status_code, 200)
        cards = response.context['cards']
        self.assertEqual(len(cards), 2)
        self.assertEqual({c['ps_pk'] for c in cards}, {self.ps_a.pk, self.ps_b.pk})
        self.assertEqual({c['prestacao_pk'] for c in cards}, {self.prestacao.pk})
        self.assertEqual({c['group_position'] for c in cards}, {'start', 'end'})

    def test_arquivar_apenas_um_servidor_nao_afeta_o_outro(self):
        from viagens_prestacoes import selectors
        self.client.post(reverse('viagens_prestacoes:prestacao_servidor_arquivar', args=[self.ps_a.pk]))
        self.ps_a.refresh_from_db()
        self.ps_b.refresh_from_db()
        self.assertTrue(self.ps_a.arquivada)
        self.assertFalse(self.ps_b.arquivada)
        self.assertIn(self.ps_a.pk, set(selectors.listar_prestacoes(aba=selectors.ABA_ARQUIVADOS).values_list('pk', flat=True)))
        self.assertIn(self.ps_b.pk, set(selectors.listar_prestacoes(aba=selectors.ABA_NAO_LIBERADAS).values_list('pk', flat=True)))

    def test_texto_rt_salvo_em_um_servidor_aparece_na_pagina_do_outro(self):
        RelatorioTecnico.objects.create(prestacao=self.prestacao, diaria='R$100,00', translado='Não houve', combustivel='Cartão Prime', passagem='Não houve', motivo='Texto compartilhado do ofício')
        data = {'diaria': 'R$100,00', 'translado': 'Não houve', 'combustivel': 'Cartão Prime', 'passagem': 'Não houve', 'motivo': 'Texto compartilhado do ofício', 'atividade': 'Atividade única do ofício', 'conclusao': '', 'medidas': '', 'info_complementares': ''}
        response = self.client.post(reverse('viagens_prestacoes:rt_servidor', args=[self.ps_a.pk]), data=data)
        self.assertEqual(response.status_code, 302)
        pagina_b = self.client.get(reverse('viagens_prestacoes:rt_servidor', args=[self.ps_b.pk]))
        self.assertEqual(pagina_b.status_code, 200)
        self.assertContains(pagina_b, 'Atividade única do ofício')
        self.assertEqual(pagina_b.context['servidores'][0]['ps_pk'], self.ps_b.pk)
        self.assertNotEqual(pagina_b.context['servidores'][0]['ps_pk'], self.ps_a.pk)
