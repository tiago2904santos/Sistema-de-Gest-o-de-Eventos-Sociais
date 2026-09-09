"""Gates públicos e preservação de evidências acrescentados na F5."""
import base64
import hashlib
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from .test_helpers import PrestacaoTestCase as TestCase
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from pypdf import PdfReader

from . import assinatura_services as svc
from .models import AssinaturaDocumento, DiarioBordo, PrestacaoDocumentoAnexo
from .test_helpers import PrestacaoFixturesMixin, pdf_minimo
from .tests_assinatura import _png_data_url


class SegurancaAssinaturaF5Tests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.setUpPrestacaoFixtures()
        fixture = self.criar_prestacao(numero=501)
        self.ps = fixture.prestacoes_servidor[0]
        self.pc = fixture.prestacao
        self.pc.oficio.motorista = self.ps.servidor
        self.pc.oficio.save(update_fields=['motorista'])
        self.orig = pdf_minimo('SNAPSHOT IMUTAVEL F5')
        with patch.object(svc, '_origem_rt_bytes', return_value=self.orig):
            self.token, docs = svc.emitir_link_rt(self.ps)
        self.doc = docs[0]
        self.anon = Client()

    def url(self, name, token=None):
        args = [token or self.token]
        if name in ('identidade', 'assinar', 'pdf_origem'):
            args.append('rt')
        return reverse('viagens_assinaturas:assinatura_'+name, args=args)

    def identificar(self, client=None):
        return (client or self.anon).post(self.url('identidade'), {'confirma_nome': '1', 'cpf': self.ps.servidor.cpf[:5]})

    def dados(self):
        return dict(png_bytes=base64.b64decode(_png_data_url().split(',')[1]), modo='fonte', fonte='classica', pagina=0, x=.2, y=.6, w=.4, h=.1)

    def assinar(self):
        self.identificar()
        svc.aplicar_assinatura(self.doc, **self.dados())

    def test_hash_sem_token_em_modelo_sessao_e_prazo_sete_dias(self):
        self.assertNotIn('link_token', {f.name for f in self.doc._meta.fields})
        self.assertEqual(self.doc.link_token_hash, hashlib.sha256(self.token.encode()).hexdigest())
        self.assertEqual(self.doc.link_expira_em-self.doc.link_criado_em, timedelta(days=7))
        self.identificar()
        self.assertNotIn(self.token, repr(dict(self.anon.session)))
        self.assertNotIn(self.token, repr(self.doc.__dict__))

    def test_invalidos_expirados_revogados_iguais_em_todas_rotas(self):
        for route in ('landing','identidade','assinar','pdf_origem','concluido'):
            invalid = self.anon.get(self.url(route, 'inexistente'))
            AssinaturaDocumento.objects.filter(pk=self.doc.pk).update(link_expira_em=timezone.now()-timedelta(seconds=1))
            expired = self.anon.get(self.url(route))
            AssinaturaDocumento.objects.filter(pk=self.doc.pk).update(link_expira_em=timezone.now()+timedelta(days=1), status='cancelada')
            revoked = self.anon.get(self.url(route))
            self.assertEqual([invalid.status_code, expired.status_code, revoked.status_code], [410]*3)
            self.assertEqual(invalid.content, expired.content)
            self.assertEqual(invalid.content, revoked.content)
            AssinaturaDocumento.objects.filter(pk=self.doc.pk).update(status='pendente')

    def test_cinco_erros_bloqueiam_apos_limpar_cache_trocar_ip_e_sessao(self):
        for _ in range(5):
            cache.clear()
            Client().post(self.url('identidade'), {'cpf': '99999', 'confirma_nome':'1'})
        cache.clear()
        response = self.anon.post(self.url('identidade'), {'cpf':self.ps.servidor.cpf[:5], 'confirma_nome':'1'}, REMOTE_ADDR='192.0.2.33')
        self.assertContains(response, 'Muitas tentativas')
        self.assertEqual(self.anon.get(self.url('pdf_origem')).status_code,403)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.tentativas_identidade,5)

    def test_csrf_continua_obrigatorio(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(self.identificar(client).status_code,403)
        client.get(self.url('identidade'))
        response=client.post(self.url('identidade'), {'confirma_nome':'1','cpf':self.ps.servidor.cpf[:5]}, HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code,302)

    def test_sem_modulo_e_senha_pendente_so_acessa_publico(self):
        user=get_user_model().objects.create_user(username='sem-viagens-f5',password='senha')
        self.anon.force_login(user)
        self.assertEqual(self.anon.post(reverse('viagens_prestacoes:assinatura_rt_gerar',args=[self.ps.pk])).status_code,403)
        user.deve_trocar_senha=True; user.save(update_fields=['deve_trocar_senha'])
        self.assertEqual(self.anon.get(self.url('landing')).status_code,200)
        self.assertEqual(self.identificar().status_code,302)

    def test_html_publico_sem_dados_da_equipe(self):
        other=self.criar_servidor('OUTRO MEMBRO SIGILOSO')
        self.pc.oficio.servidores.add(other)
        self.ps.servidor.telefone='41999998888'; self.ps.servidor.save(update_fields=['telefone'])
        for route in ('landing','identidade'):
            r=self.anon.get(self.url(route))
            for private in (self.ps.servidor.cpf, '41999998888', other.nome):
                self.assertNotContains(r,private)
            self.assertEqual(r['Referrer-Policy'],'same-origin')
            self.assertIn('no-store',r['Cache-Control'])

    def test_snapshot_codigo_hash_e_recusa_segundo_carimbo(self):
        self.assinar()
        with self.doc.arquivo_assinado.open('rb') as f: signed=f.read()
        self.assertEqual(self.doc.hash_assinado,hashlib.sha256(signed).hexdigest())
        self.assertIn(self.doc.codigo_verificacao,PdfReader(BytesIO(signed)).pages[0].extract_text())
        with self.doc.arquivo_origem.open('rb') as f: self.assertEqual(f.read(),self.orig)
        with self.assertRaises(svc.AssinaturaError): svc.aplicar_assinatura(self.doc,**self.dados())
        self.assertEqual(svc.pdf_rt_assinado_ou_gerado(self.ps),signed)

    def test_nome_longo_nao_corta_codigo_de_verificacao(self):
        AssinaturaDocumento.objects.filter(pk=self.doc.pk).update(nome_esperado='NOME MUITO LONGO ' * 14)
        self.assinar()
        with self.doc.arquivo_assinado.open('rb') as f:
            texto=PdfReader(f).pages[0].extract_text()
        self.assertIn(self.doc.codigo_verificacao,texto)

    def test_snapshot_adulterado_e_recusado(self):
        self.identificar()
        Path(self.doc.arquivo_origem.path).write_bytes(pdf_minimo('CONTEUDO ALTERADO'))
        with self.assertRaisesMessage(svc.AssinaturaError,'foi alterado'):
            svc.aplicar_assinatura(self.doc,**self.dados())
        self.doc.refresh_from_db(); self.assertFalse(self.doc.arquivo_assinado)

    def test_reemissao_preserva_evidencia_e_revoga_token_anterior(self):
        self.assinar()
        previous=self.doc.arquivo_assinado.name
        with patch.object(svc,'_origem_rt_bytes',return_value=pdf_minimo('NOVA EMISSAO')):
            token,docs=svc.emitir_link_rt(self.ps,forcar=True)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status,'cancelada')
        self.assertTrue(self.doc.arquivo_assinado.storage.exists(previous))
        self.assertNotEqual(docs[0].pk,self.doc.pk)
        self.assertEqual(svc.documentos_do_link(self.token),[])
        self.assertEqual(len(svc.documentos_do_link(token)),1)
        r=self.anon.get(reverse('viagens_assinaturas:verificar',args=[self.doc.codigo_verificacao]))
        self.assertContains(r,'revogada')

    def test_png_invalido_opaco_vazio_e_coordenadas_invalidas_nao_gravam(self):
        self.identificar()
        invalidos=[b'fake png']
        for color in ((0,0,0,0),(0,0,0,255)):
            buf=BytesIO(); Image.new('RGBA',(20,20),color).save(buf,format='PNG'); invalidos.append(buf.getvalue())
        for png in invalidos:
            with self.assertRaises(svc.AssinaturaError): svc.aplicar_assinatura(self.doc,**{**self.dados(),'png_bytes':png})
        for fields in ({'x':float('nan')},{'w':2},{'pagina':1},{'x':.9}):
            with self.assertRaises(svc.AssinaturaError): svc.aplicar_assinatura(self.doc,**{**self.dados(),**fields})
        self.doc.refresh_from_db(); self.assertFalse(self.doc.arquivo_assinado)

    def test_falha_de_banco_apos_gravar_pdf_remove_so_arquivos_novos(self):
        self.identificar()
        folder=Path(self.doc.arquivo_origem.path).parent
        before=set(folder.rglob('*'))
        with patch.object(AssinaturaDocumento,'save',side_effect=RuntimeError('falha injetada')):
            with self.assertRaises(RuntimeError): svc.aplicar_assinatura(self.doc,**self.dados())
        self.assertEqual(set(folder.rglob('*')),before)
        self.doc.refresh_from_db(); self.assertEqual(self.doc.status,'pendente')

    def test_upload_assinado_tem_prioridade_sobre_eletronico(self):
        from .download_services import pdf_assinado,payload_downloads
        self.assinar()
        self.assertEqual(pdf_assinado(self.ps,'rt'),svc.pdf_rt_assinado_ou_gerado(self.ps))
        rt=next(i for i in payload_downloads(self.ps)['itens'] if i['id']=='rt')
        self.assertTrue(rt['versoes']['assinado']['pdf'])
        upload=pdf_minimo('ASSINADO EXTERNO PRIORITARIO')
        PrestacaoDocumentoAnexo.objects.create(prestacao=self.pc,servidor_prestacao=self.ps,tipo=PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO,arquivo=SimpleUploadedFile('rt.pdf',upload))
        self.assertEqual(pdf_assinado(self.ps,'rt'),upload)

    def test_diario_assina_motorista_efetivo(self):
        other=self.criar_servidor('MOTORISTA AJUSTADO')
        diario=DiarioBordo.objects.create(prestacao=self.pc,motorista_modo=DiarioBordo.MOTORISTA_MODO_SERVIDOR,motorista_servidor=other)
        self.pc.refresh_from_db(); self.assertEqual(svc.signer_db(self.pc),other)
        diario.motorista_modo=DiarioBordo.MOTORISTA_MODO_OUTRO; diario.save()
        self.pc.refresh_from_db(); self.assertIsNone(svc.signer_db(self.pc))

    def test_throttle_publico_geral(self):
        for _ in range(120): response=self.anon.get(self.url('landing','inexistente'))
        response=self.anon.get(self.url('landing','inexistente'))
        self.assertEqual(response.status_code,429)
        self.assertEqual(response['Retry-After'],'60')
