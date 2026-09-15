from cadastros.models import Regiao
import io
import tempfile
from datetime import date, datetime, timedelta, timezone as utc
from decimal import Decimal
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from docx import Document
from accounts.models import Modulo, Setor
from cadastros.models import Estado, Municipio
from viagens_cadastros.models import Servidor, Cargo, Unidade, Viatura, ConfiguracaoSistema, AssinaturaConfiguracao
from viagens_roteiros.models import Roteiro, RoteiroDestino, RoteiroTrecho
from viagens_oficios.models import Oficio, ModeloMotivoOficio, Justificativa
from viagens_oficios.forms import OficioForm, ModeloMotivoOficioForm
from viagens_oficios.document_generation import gerar_documento
from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context
from viagens_termos.models import TermoAutorizacao
from viagens_termos.forms import TermoAutorizacaoForm
from viagens_termos.services import gerar_termo_lote, gerar_termo_cadastro_um, build_termo_cadastro_payload, VarianteTermo
from documentos.models import DocumentoArtefato
from documentos.services.types import DocumentoFormato


class IntegracaoF4Tests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=folder.name, DOCUMENTOS_DEFAULT_PDF_ENGINE='simple'))
        self.user = get_user_model().objects.create_user(username='operador-f4', deve_trocar_senha=False)
        self.setor = Setor.objects.create(nome='Setor F4')
        Modulo.objects.get(codigo='VIAGENS').setores.add(self.setor)
        self.user.setores.add(self.setor)
        self.user.groups.add(Group.objects.get(name='VIAGENS_OPERADOR'))
        self.client.force_login(self.user)
        self.uf = Estado.objects.get_or_create(sigla='PR', defaults={'nome':'Paraná', 'codigo_ibge':41})[0]
        self.sede = Municipio.objects.get_or_create(codigo_ibge=4106902, defaults={'nome':'Curitiba', 'estado':self.uf, 'regiao':Regiao.objects.get_or_create(nome='Interior')[0]})[0]
        self.destino = Municipio.objects.get_or_create(codigo_ibge=4113700, defaults={'nome':'Londrina', 'estado':self.uf, 'regiao':Regiao.objects.get_or_create(nome='Interior')[0]})[0]
        self.cargo = Cargo.objects.create(nome='Investigador')
        self.unidade = Unidade.objects.create(nome='Unidade F4')
        self.a = Servidor.objects.create(nome='ANA TESTE', cargo=self.cargo, unidade=self.unidade, cpf='11122233344')
        self.b = Servidor.objects.create(nome='BRUNO TESTE', cargo=self.cargo, unidade=self.unidade, cpf='55566677788')
        self.viatura = Viatura.objects.create(placa='ABC1D23', modelo='VEÍCULO F4')
        self.saida = timezone.make_aware(datetime(2026, 9, 10, 8))
        self.roteiro = Roteiro.objects.create(origem_municipio=self.sede, saida_dt=self.saida,
            retorno_chegada_dt=self.saida+timedelta(hours=24), valor_diarias=Decimal('43.58'), resumo_diarias='1 x 100%')
        RoteiroDestino.objects.create(roteiro=self.roteiro, municipio=self.destino)
        RoteiroTrecho.objects.create(roteiro=self.roteiro, origem_municipio=self.sede, destino_municipio=self.destino,
            saida_dt=self.saida, chegada_dt=self.saida+timedelta(hours=4))
        self.cfg = ConfiguracaoSistema.get_singleton()
        self.cfg.unidade = self.unidade
        self.cfg.save()
        AssinaturaConfiguracao.objects.create(configuracao=self.cfg, tipo='OFICIO', servidor=self.b)

    def payload(self):
        return {'data_criacao': '2026-09-09', 'protocolo': '12.345.678-9', 'motivo': 'Missão F4',
                'custeio': 'UNIDADE_DPC', 'servidores': [str(self.a.pk), str(self.b.pk)],
                'servidores_termo_autorizacao': [str(self.a.pk), str(self.b.pk)],
                'viatura': self.viatura.pk, 'motorista': self.a.pk, 'motorista_modo': 'SERVIDOR',
                'roteiro': self.roteiro.pk, 'justificativa-texto': 'Solicitação recebida nesta data.'}

    def criar(self):
        response = self.client.post(reverse('viagens_oficios:novo'), self.payload())
        self.assertEqual(response.status_code, 302, response.content[:2000])
        return Oficio.objects.latest('pk')

    def test_ciclo_completo_interface_docx_pdf_arquivar_cancelar_reativar(self):
        o = self.criar()
        self.assertEqual(o.status, 'RASCUNHO')
        for formato in ['docx', 'pdf']:
            resposta = self.client.post(reverse('viagens_oficios:gerar', args=[o.pk, 'oficio', formato]))
            self.assertEqual(resposta.status_code, 200)
            self.assertTrue(resposta.content.startswith(b'PK' if formato == 'docx' else b'%PDF'))
        o.refresh_from_db()
        self.assertEqual(o.status, 'GERADO')
        for acao in ['arquivar', 'cancelar', 'reativar']:
            self.assertEqual(self.client.post(reverse('viagens_oficios:acao', args=[o.pk, acao])).status_code, 302)
        o.refresh_from_db()
        self.assertEqual(o.status, 'ARQUIVADO')
        self.assertFalse(o.cancelado)
        self.assertEqual(o.artefatos.count(), 2)

    def test_lote_individual_nome_variante_e_vinculos(self):
        o = self.criar()
        docs = gerar_termo_lote(o, DocumentoFormato.DOCX)
        self.assertEqual(len(docs), 2)
        for doc, pessoa in zip(docs, [self.a, self.b]):
            art = DocumentoArtefato.objects.get(pk=doc.artefato_id)
            self.assertEqual(art.oficio_id, o.pk)
            self.assertEqual(art.servidor_id, pessoa.pk)
            self.assertEqual(art.payload_snapshot['termo']['variante'], VarianteTermo.COMPLETO_COM_VIATURA)
            with ZipFile(io.BytesIO(doc.conteudo)) as z:
                xml = z.read('word/document.xml').decode()
            self.assertIn(pessoa.nome, xml)

    def test_cache_inclui_oficio_e_termo(self):
        o = self.criar()
        termos = [TermoAutorizacao.objects.create(oficio=o) for _ in range(2)]
        a = gerar_termo_cadastro_um(termos[0], self.a, DocumentoFormato.DOCX)
        b = gerar_termo_cadastro_um(termos[1], self.a, DocumentoFormato.DOCX)
        repetido = gerar_termo_cadastro_um(termos[0], self.a, DocumentoFormato.DOCX)
        self.assertNotEqual(a.artefato_id, b.artefato_id)
        self.assertEqual(a.artefato_id, repetido.artefato_id)
        self.assertTrue(repetido.cache_hit)

    def test_snapshot_sobrevive_exclusao(self):
        o = self.criar()
        self.b.delete()
        o.refresh_from_db()
        self.assertEqual(o.diarias_para_servidores()['valor_decimal'], Decimal('87.16'))

    def test_total_da_f2_nao_multiplica_efetivo_duas_vezes(self):
        self.roteiro.quantidade_servidores = 3
        self.roteiro.valor_diarias = Decimal('130.74')
        self.roteiro.save()
        o = self.criar()
        self.assertEqual(o.diarias_para_servidores()['valor_decimal'], Decimal('87.16'))
        self.assertIn('87,16', build_oficio_docxtpl_context(o)['diaria'])

    def test_divisao_nao_exata_arredonda_em_centavos(self):
        """Dinheiro não pode sair da divisão com 28 casas.

        O valor entra no snapshot do artefato e é herdado por quem consome o
        ofício depois; arredondar só na hora de imprimir deixa o instantâneo
        com 33,33333... gravado.
        """
        self.roteiro.quantidade_servidores = 3
        self.roteiro.valor_diarias = Decimal('100.00')
        self.roteiro.save()
        valor = self.criar().diarias_para_servidores()['valor_decimal']
        self.assertEqual(valor, Decimal('66.66'))
        self.assertEqual(valor.as_tuple().exponent, -2)

    def test_efetivo_igual_ao_do_roteiro_preserva_o_total_da_f2(self):
        """Dividir e multiplicar de volta devolvia 99,999... no lugar de 100,00."""
        self.roteiro.quantidade_servidores = 2
        self.roteiro.valor_diarias = Decimal('100.00')
        self.roteiro.save()
        self.assertEqual(
            self.criar().diarias_para_servidores()['valor_decimal'], Decimal('100.00')
        )

    def test_horario_local_no_documento(self):
        o = self.criar()
        o = Oficio.objects.get(pk=o.pk)
        ctx = build_oficio_docxtpl_context(o)
        self.assertIn('10/09/2026 08:00', ctx['col_ida_saida'])
        self.assertNotIn('11:00', ctx['col_ida_saida'])
        self.assertIn('87,16', ctx['diaria'])
        self.assertEqual(ctx['nome_chefia'], 'Bruno Teste')

    def test_termo_herda_valores(self):
        o = self.criar()
        t = TermoAutorizacao.objects.create(oficio=o)
        self.assertEqual(t.periodo_efetivo(), (date(2026, 9, 10), date(2026, 9, 11)))
        self.assertIn('Londrina', t.destino_efetivo())
        self.assertEqual(set(t.servidores_efetivos()), {self.a, self.b})
        self.assertEqual(t.viatura_efetiva(), self.viatura)

    def test_termo_herda_horarios_gravados_somente_em_trechos_f2(self):
        self.roteiro.saida_dt = None
        self.roteiro.retorno_chegada_dt = None
        self.roteiro.save()
        t = TermoAutorizacao.objects.create(oficio=self.criar())
        self.assertEqual(t.periodo_efetivo(), (date(2026, 9, 10), date(2026, 9, 10)))
        self.assertIn('10 de setembro', build_termo_cadastro_payload(t, self.a)['termo']['viagem']['periodo'])

    def test_termo_preenchido_prevalece(self):
        o = self.criar()
        t = TermoAutorizacao.objects.create(oficio=o, destino_cidade=self.sede,
            data_evento_inicio=date(2026, 10, 1), data_evento_fim=date(2026, 10, 2))
        t.servidores.add(self.b)
        self.assertIn('Curitiba', t.destino_efetivo())
        self.assertEqual(t.periodo_efetivo(), (date(2026, 10, 1), date(2026, 10, 2)))
        self.assertEqual(list(t.servidores_efetivos()), [self.b])
        payload = build_termo_cadastro_payload(t, self.b)
        self.assertIn('Curitiba', payload['termo']['viagem']['destinos_texto'])

    def test_termo_avulso_sem_viatura(self):
        t = TermoAutorizacao.objects.create(destino_cidade=self.sede, data_evento_inicio=date(2026, 10, 1))
        t.servidores.add(self.a)
        self.assertEqual(build_termo_cadastro_payload(t, self.a)['termo']['variante'], VarianteTermo.COMPLETO_SEM_VIATURA)

    def test_periodo_termo_respeita_virada_dia_local(self):
        self.roteiro.saida_dt = datetime(2026, 9, 11, 1, tzinfo=utc.utc)
        self.roteiro.save()
        t = TermoAutorizacao.objects.create(oficio=self.criar())
        self.assertEqual(t.periodo_efetivo()[0], date(2026, 9, 10))

    def test_telas_operacionais(self):
        o = self.criar()
        t = TermoAutorizacao.objects.create(oficio=o)
        rotas = [('viagens_oficios:lista', []), ('viagens_oficios:novo', []),
                 ('viagens_oficios:editar', [o.pk]),
                 ('viagens_oficios:catalogo', ['motivos']), ('viagens_oficios:catalogo_novo', ['motivos']),
                 ('viagens_oficios:catalogo', ['justificativas']), ('viagens_oficios:catalogo_novo', ['justificativas']),
                 ('viagens_termos:lista', []), ('viagens_termos:novo', []), ('viagens_termos:editar', [t.pk]),
                 ('viagens_termos:editar', [t.pk]), ('viagens_termos:preview', [t.pk])]
        for nome, args in rotas:
            with self.subTest(nome=nome):
                self.assertEqual(self.client.get(reverse(nome, args=args)).status_code, 200)

    def test_sem_modulo_403(self):
        self.user.setores.clear()
        for url in ['viagens_oficios:lista', 'viagens_oficios:novo', 'viagens_termos:lista', 'viagens_termos:novo']:
            self.assertEqual(self.client.get(reverse(url)).status_code, 403)

    def test_leitor_consulta_mas_nao_cria_edita_nem_gera(self):
        # Sem tela de detalhe, o ofício tem uma tela só — o formulário — e ela é
        # de operador. O leitor continua chegando à lista e nada mais.
        o = self.criar()
        self.user.groups.clear()
        self.assertEqual(self.client.get(reverse('viagens_oficios:lista')).status_code, 200)
        self.assertEqual(self.client.get(reverse('viagens_oficios:editar', args=[o.pk])).status_code, 403)
        for name,args in [('viagens_oficios:novo',[]),('viagens_oficios:editar',[o.pk]),('viagens_termos:novo',[])]:
            self.assertEqual(self.client.post(reverse(name,args=args), self.payload()).status_code,403)
        self.assertEqual(self.client.post(reverse('viagens_oficios:gerar',args=[o.pk,'oficio','docx'])).status_code,403)

    def test_numeracao_e_institucional_apenas_gestor(self):
        for name in ['viagens_oficios:numeracao', 'viagens_oficios:institucional']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.user.groups.add(Group.objects.get(name='VIAGENS_GESTOR'))
        for name in ['viagens_oficios:numeracao', 'viagens_oficios:institucional']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.post(reverse('viagens_oficios:numeracao'), {'ano':2026,'numero_inicial':100}).status_code,302)
        self.assertEqual(self.criar().numero, 100)

    def test_catalogo_troca_padrao(self):
        ModeloMotivoOficio.objects.create(nome='Primeiro', texto='A', is_padrao=True)
        form = ModeloMotivoOficioForm({'nome':'Segundo','texto':'B','ativo':'on','is_padrao':'on','ordem':100})
        self.assertTrue(form.is_valid(),form.errors)
        form.save()
        self.assertEqual(ModeloMotivoOficio.objects.get(is_padrao=True).nome,'SEGUNDO')

    def test_avulso_exige_destino_periodo(self):
        f = TermoAutorizacaoForm({})
        self.assertFalse(f.is_valid())
        self.assertIn('destino_cidade', f.errors)
        self.assertIn('data_evento_inicio', f.errors)

    def test_form_rejeita_protocolo_cru_longo(self):
        payload = self.payload()
        payload['protocolo'] = '.' * 40 + '123456789'
        f = OficioForm(payload)
        self.assertFalse(f.is_valid())
        self.assertIn('protocolo',f.errors)

    def test_auditoria_guarda_criacao_e_cancelamento(self):
        from auditoria.models import RegistroAuditoria
        with self.captureOnCommitCallbacks(execute=True):
            o = self.criar()
            self.client.post(reverse('viagens_oficios:acao',args=[o.pk,'cancelar']),{'motivo':'Teste'})
        registros = RegistroAuditoria.objects.filter(modelo='viagens_oficios.oficio',objeto_id=str(o.pk),usuario=self.user)
        self.assertTrue(registros.exists())
        self.assertTrue(any('cancelado' in r.alteracoes for r in registros))

    def test_editar_metadados_apos_exclusao_preserva_snapshot(self):
        o = self.criar()
        self.b.delete()
        payload = self.payload()
        payload.update(servidores=[self.a.pk], servidores_termo_autorizacao=[self.a.pk], motivo='Só metadados')
        self.assertEqual(self.client.post(reverse('viagens_oficios:editar', args=[o.pk]), payload).status_code, 302)
        o.refresh_from_db()
        self.assertEqual(o.diarias_quantidade_servidores, 2)
        self.assertEqual(o.diarias_para_servidores()['valor_decimal'], Decimal('87.16'))

    def test_mudar_equipe_recalcula_snapshot(self):
        o = self.criar()
        payload = self.payload()
        payload.update(servidores=[self.a.pk], servidores_termo_autorizacao=[self.a.pk])
        self.client.post(reverse('viagens_oficios:editar', args=[o.pk]), payload)
        o.refresh_from_db()
        self.assertEqual(o.diarias_quantidade_servidores, 1)

    def test_transporte_manual_exige_referencia_do_motorista(self):
        from viagens_oficios.services import validar_oficio_para_documento
        o = self.criar()
        o.viatura = None
        o.transporte_placa_manual = 'ABC1234'
        o.motorista = None
        o.motorista_modo = Oficio.MOTORISTA_MODO_MANUAL
        o.motorista_manual_nome = 'Externo'
        self.assertEqual(validar_oficio_para_documento(o)['checks']['motorista_documento'], 'incomplete')
        o.motorista_oficio_referencia = '02/2026'
        o.motorista_protocolo_ref = '123456789'
        self.assertEqual(validar_oficio_para_documento(o)['status'], 'complete')

    def test_motorista_cadastrado_fora_equipe_exige_referencia(self):
        from viagens_oficios.services import pendencias_motorista_documento
        o = self.criar()
        o.servidores.remove(self.a)
        self.assertEqual(len(pendencias_motorista_documento(o)), 2)
        o.motorista_oficio_referencia = '02/2026'
        o.motorista_protocolo_ref = '123456789'
        self.assertEqual(pendencias_motorista_documento(o), [])

    def test_cancelado_nao_gera_e_retificado_complementar_exclusivos(self):
        from viagens_oficios.services import retificar_oficio, marcar_oficio_complementar
        from django.core.exceptions import ValidationError
        o = self.criar()
        retificar_oficio(o)
        marcar_oficio_complementar(o)
        self.assertFalse(o.retificado_documento)
        self.assertTrue(o.complementar_documento)
        o.cancelar('Teste')
        with self.assertRaises(ValidationError):
            gerar_documento(o, DocumentoFormato.DOCX)

    def test_erro_documental_amigavel_nas_duas_origens_de_termo(self):
        from unittest.mock import patch
        from documentos.services.exceptions import DocumentError
        o = self.criar()
        t = TermoAutorizacao.objects.create(oficio=o)
        for name, args, alvo in [
            ('viagens_oficios:termo', [o.pk, self.a.pk, 'pdf'], 'viagens_termos.services.gerar_termo_um'),
            ('viagens_termos:gerar', [t.pk, self.a.pk, 'pdf'], 'viagens_termos.views.gerar_termo_cadastro_um'),
        ]:
            with self.subTest(name=name), patch(alvo, side_effect=DocumentError('Motor temporariamente indisponível')):
                r = self.client.post(reverse(name, args=args), follow=True)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, 'Motor temporariamente indisponível')

    def test_termo_avulso_crud_datas_destinos_e_generico(self):
        payload = {'destino_estado': self.uf.pk, 'destino_cidade': self.destino.pk,
                   'data_evento_inicio': '2026-10-01', 'data_evento_fim': '2026-10-02'}
        self.assertEqual(self.client.post(reverse('viagens_termos:novo'), payload).status_code, 302)
        t = TermoAutorizacao.objects.get()
        self.assertEqual(build_termo_cadastro_payload(t)['termo']['variante'], VarianteTermo.SEMIPREENCHIDO)
        r = self.client.post(reverse('viagens_termos:lote', args=[t.pk, 'docx']))
        with ZipFile(io.BytesIO(r.content)) as z:
            self.assertEqual(len(z.namelist()), 1)
        payload['data_evento_fim'] = '2026-09-01'
        f = TermoAutorizacaoForm(payload)
        self.assertFalse(f.is_valid())
        self.assertIn('data_evento_fim', f.errors)

    def test_adicionar_destino_preserva_dados_sem_gravar(self):
        r = self.client.post(reverse('viagens_termos:novo'), {
            'acao': 'adicionar_destino', 'quantidade_destinos': '3',
            'destino_estado': self.uf.pk, 'destino_cidade': self.destino.pk,
            'data_evento_inicio': '2026-10-01',
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'extra_cidade_3')
        self.assertFalse(TermoAutorizacao.objects.exists())

    def test_termo_rejeita_municipio_de_outro_estado(self):
        outra = Estado.objects.get_or_create(sigla='SC', defaults={'nome':'Santa Catarina', 'codigo_ibge':42})[0]
        f = TermoAutorizacaoForm({'destino_estado': outra.pk, 'destino_cidade': self.destino.pk, 'data_evento_inicio':'2026-10-01'})
        self.assertFalse(f.is_valid())
        self.assertIn('destino_cidade', f.errors)

    def test_assinado_download_preview_e_revogacao_preservam_historico(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        o = self.criar()
        doc = gerar_termo_cadastro_um(TermoAutorizacao.objects.create(oficio=o), self.a, DocumentoFormato.PDF)
        art = DocumentoArtefato.objects.get(pk=doc.artefato_id)
        url = reverse('viagens_oficios:assinatura_artefato', args=[art.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        assinado = b'%PDF-1.4\nVERSAO ASSINADA\n%%EOF'
        r = self.client.post(url, {'arquivo': SimpleUploadedFile('assinado.pdf', assinado, content_type='application/pdf')})
        self.assertEqual(r.status_code, 302)
        for name in ['viagens_oficios:preview_artefato', 'documentos:baixar']:
            r = self.client.get(reverse(name, args=[art.pk]))
            self.assertEqual(b''.join(r.streaming_content), assinado)
        self.client.post(url, {'acao':'remover'})
        art.refresh_from_db()
        self.assertFalse(art.esta_assinado)
        self.assertEqual(art.versoes_assinadas.count(), 1)
        self.assertIsNotNone(art.versoes_assinadas.get().revogada_em)

    def test_justificativa_form_obrigatoria_e_modelo_opcional(self):
        from viagens_oficios.forms import JustificativaForm
        for obrigatoria, texto, valido in [(True,'',False),(False,'',True),(True,'Motivo tempestivo',True)]:
            f = JustificativaForm({'texto':texto}, obrigatoria=obrigatoria)
            self.assertEqual(f.is_valid(), valido)
