"""Fatia 3/6 de T-01 — comprovante, anexos e o acesso ao arquivo privado.

Esta fatia guarda a promessa mais delicada do módulo: **arquivo anexado a uma
prestação não é público**. A auditoria de segurança de 27/07 abriu com
justamente esse risco — mídia privada servida direto pelo Nginx, sem passar por
autenticação. A view existe para ser o portão; estes testes provam que ela é.

Como as demais fatias, aqui se fotografa o comportamento atual. Defeito
encontrado vira linha ``NOVO``; correção é outro PR.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
from pathlib import Path
from django.core.files.uploadedfile import SimpleUploadedFile
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes.models import PrestacaoDocumentoAnexo
from viagens_prestacoes.models import PrestacaoServidor
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin
PDF = pdf_minimo()

def arquivo(nome='comprovante.pdf', conteudo=PDF):
    return SimpleUploadedFile(nome, conteudo, content_type='application/pdf')

class AnexoUploadTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.ps = self.fixture.prestacoes_servidor[0]

    def enviar(self, ps=None, **arquivos):
        ps = ps or self.ps
        dados = {f'ps-{ps.pk}-{campo}': valor for campo, valor in arquivos.items()}
        return self.client.post(reverse('viagens_prestacoes:prestacao_servidor_arquivo_autosave', args=[ps.pk]), dados)

    def test_upload_cria_anexo_com_tipo_e_nome_original(self):
        response = self.enviar(comprovante_arquivos=arquivo('Saque Agosto.pdf'))
        self.assertTrue(response.json()['ok'])
        anexo = self.ps.documentos_anexos.get()
        self.assertEqual(anexo.tipo, PrestacaoDocumentoAnexo.TIPO_COMPROVANTE)
        self.assertEqual(anexo.nome_original, 'Saque Agosto.pdf')
        self.assertTrue(anexo.arquivo.name)

    def test_upload_avanca_status_para_em_preenchimento(self):
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_PENDENTE)
        self.enviar(comprovante_arquivos=arquivo())
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO)

    def test_upload_nao_apaga_numero_de_solicitacao_ja_gravado(self):
        """O autosave de arquivo salva só anexos — é o contrato declarado na view."""
        PrestacaoServidor.objects.filter(pk=self.ps.pk).update(numero_solicitacao='A-99')
        self.enviar(comprovante_arquivos=arquivo())
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.numero_solicitacao, 'A-99')

    def test_extensao_nao_permitida_e_recusada_sem_criar_anexo(self):
        response = self.enviar(comprovante_arquivos=SimpleUploadedFile('malicioso.exe', b'MZ', content_type='application/octet-stream'))
        corpo = response.json()
        self.assertFalse(corpo['ok'])
        self.assertEqual(corpo['message'], 'Alguns anexos ainda precisam de ajuste antes do autosave.')
        self.assertEqual(self.ps.documentos_anexos.count(), 0)

class AnexoConteudoTests(PrestacaoFixturesMixin, TestCase):
    """O portão do arquivo privado."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.ps = self.fixture.prestacoes_servidor[0]
        self.anexo = PrestacaoDocumentoAnexo.objects.create(prestacao=self.fixture.prestacao, servidor_prestacao=self.ps, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE, arquivo=arquivo('sigiloso.pdf'), nome_original='sigiloso.pdf')

    def url(self, prestacao=None, anexo=None):
        return reverse('viagens_prestacoes:prestacao_documento_conteudo', args=[(prestacao or self.fixture.prestacao).pk, (anexo or self.anexo).pk])

    def test_conteudo_exige_autenticacao_e_redireciona_ao_login(self):
        """Sem sessão o arquivo não sai — é o ponto do defeito de mídia pública.

        Afirma o mecanismo, não só a ausência do arquivo: o anônimo é mandado
        ao login com ``next`` preservado. Um 404 também "protegeria", mas por
        acidente do isolamento por área — e passaria a esconder uma regressão
        no dia em que o portão de autenticação saísse.
        """
        url = self.url()
        self.client.logout()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], f"{reverse('accounts:login')}?next={url}")
        self.assertNotIn(b'%PDF', response.content)

class AnexoExclusaoTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.ps = self.fixture.prestacoes_servidor[0]
        self.anexo = PrestacaoDocumentoAnexo.objects.create(prestacao=self.fixture.prestacao, servidor_prestacao=self.ps, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE, arquivo=arquivo('para-excluir.pdf'), nome_original='para-excluir.pdf')

    def url(self, prestacao=None, anexo=None):
        return reverse('viagens_prestacoes:prestacao_documento_delete', args=[(prestacao or self.fixture.prestacao).pk, (anexo or self.anexo).pk])

    def test_exclusao_remove_registro_e_o_arquivo_do_disco(self):
        caminho = Path(self.anexo.arquivo.path)
        self.assertTrue(caminho.exists())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url())
        self.assertTrue(response.json()['ok'])
        self.assertFalse(PrestacaoDocumentoAnexo.objects.filter(pk=self.anexo.pk).exists())
        self.assertFalse(caminho.exists())

    def test_exclusao_por_get_e_recusada_e_o_anexo_sobrevive(self):
        """BE-02 — apagar é efeito colateral; `GET` não pode causá-lo.

        Sem `@require_POST`, qualquer requisição autenticada apagava o anexo e o
        arquivo do storage: prefetch do navegador, `<img src>` em página de terceiro,
        crawler interno, link colado em chat. Prestação não tem lixeira.
        """
        caminho = Path(self.anexo.arquivo.path)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 405)
        self.assertTrue(PrestacaoDocumentoAnexo.objects.filter(pk=self.anexo.pk).exists())
        self.assertTrue(caminho.exists())

    def test_exclusao_marca_servidor_em_preenchimento(self):
        self.client.post(self.url())
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO)
