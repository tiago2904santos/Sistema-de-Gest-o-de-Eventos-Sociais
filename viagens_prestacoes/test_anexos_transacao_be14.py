"""`BE-14` fatia 3 — rede para os anexos assinados, onde a transação sozinha **piora**.

Esta é a fatia que o catálogo mandou tratar com cuidado, e o motivo é que aqui o banco
não é o único lugar que guarda estado: o **storage** também. E storage não faz rollback.

Duas funções de `document_views.py` misturam os dois:

- `_prestacao_assinado_upload` apaga os arquivos anteriores do disco, apaga as linhas, e
  **depois** cria a linha nova. Se o `create` falhar, o documento assinado anterior sumiu
  do disco *e* do banco. **Não volta.** É o cenário 1, e ele reprova hoje.
- `prestacao_documento_excluir` apaga a linha e depois o arquivo, nessa ordem, por causa
  do `BE-07`: apagar o arquivo primeiro zera `FieldFile.name`, e com `nome_original`
  vazio o `__str__` do anexo devolvia `None`, derrubando o sinal de auditoria no
  `pre_delete`. A ordem é deliberada e tem teste próprio em
  `core/tests/test_audit_repr_defensivo.py`.

**Por que `atomic` sozinho seria pior.** Envolver a exclusão numa transação sem mais nada
faz o `arquivo.delete()` rodar dentro dela. Um rollback depois disso devolve a linha ao
banco com o arquivo já destruído no disco — o **inverso exato** do órfão que o `BE-07`
corrigiu, e igualmente irrecuperável.

O par que fecha os dois é `atomic` (linha) + `transaction.on_commit` (arquivo). O padrão
já existe no repositório em `core/audit.py:156,170` e em `integracoes/google_drive`; aqui
ele passa a valer para `FieldFile.delete`, que é uso novo.

**Consequência para quem escreve teste:** `on_commit` não dispara dentro de `TestCase`,
que envolve cada teste numa transação desfeita no fim. Provar que o arquivo saiu do disco
exige `captureOnCommitCallbacks(execute=True)` — e é por isso que o teste antigo
`test_anexos.py::test_exclusao_remove_registro_e_o_arquivo_do_disco` muda de forma nesta
fatia sem mudar de intenção.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
from pathlib import Path
from unittest import mock
from django.core.files.uploadedfile import SimpleUploadedFile
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes.models import PrestacaoDocumentoAnexo
from viagens_prestacoes.models import PrestacaoServidor
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin
PDF = pdf_minimo()

def arquivo(nome='assinado.pdf', conteudo=PDF):
    return SimpleUploadedFile(nome, conteudo, content_type='application/pdf')

class UploadDeAssinadoNaoPodeDestruirOAnteriorTests(PrestacaoFixturesMixin, TestCase):
    """Substituir um documento assinado não pode custar o que já estava lá."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=61)
        self.prestacao = self.fixture.prestacao
        # O RT assinado é o que se substitui; despacho e comprovante somam (m081).
        self.ps = self.fixture.prestacoes_servidor[0]
        self.anterior = PrestacaoDocumentoAnexo.objects.create(prestacao=self.prestacao, servidor_prestacao=self.ps, tipo=PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO, arquivo=arquivo('rt-antigo.pdf'), nome_original='rt-antigo.pdf')

    def enviar(self):
        return self.client.post(reverse('viagens_prestacoes:prestacao_servidor_assinado_anexar', args=[self.ps.pk, PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO]), {'arquivo': arquivo('rt-novo.pdf')})

    def test_substituicao_bem_sucedida_troca_o_anexo(self):
        caminho_antigo = Path(self.anterior.arquivo.path)
        self.assertTrue(caminho_antigo.exists())
        self.enviar()
        restantes = PrestacaoDocumentoAnexo.objects.filter(prestacao=self.prestacao, tipo=PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO)
        self.assertEqual(restantes.count(), 1)
        self.assertEqual(restantes.first().nome_original, 'rt-novo.pdf')

    def test_falha_ao_criar_o_novo_nao_pode_destruir_o_anterior(self):
        """**Perda de dado, e reprova hoje.**

        A ordem de hoje apaga os arquivos anteriores do disco e as linhas **antes** de
        criar a linha nova. Se o `create` falhar — erro de storage, disco cheio, erro de
        banco —, o documento assinado anterior não existe mais em lugar nenhum. Não é
        gravação parcial: é destruição.

        Reprovava no commit da rede; passou a valer quando a exclusão das linhas foi
        para dentro da transação e a dos arquivos para o `on_commit`.
        """
        caminho_antigo = Path(self.anterior.arquivo.path)
        original = PrestacaoDocumentoAnexo.save

        def falhar_no_insert(self_anexo, *args, **kwargs):
            if self_anexo.pk is None:
                raise RuntimeError('falha ao criar o anexo novo')
            return original(self_anexo, *args, **kwargs)
        with mock.patch.object(PrestacaoDocumentoAnexo, 'save', falhar_no_insert):
            with self.assertRaises(RuntimeError):
                self.enviar()
        self.assertTrue(PrestacaoDocumentoAnexo.objects.filter(pk=self.anterior.pk).exists(), 'a linha do anexo anterior foi apagada e a nova não entrou')
        self.assertTrue(caminho_antigo.exists(), 'o arquivo do anexo anterior foi destruído no disco e não volta')

class ExclusaoDeAnexoTests(PrestacaoFixturesMixin, TestCase):
    """A exclusão, e a ordem que o `BE-07` fixou."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=62)
        self.ps = self.fixture.prestacoes_servidor[0]
        self.anexo = PrestacaoDocumentoAnexo.objects.create(prestacao=self.fixture.prestacao, servidor_prestacao=self.ps, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE, arquivo=arquivo('para-excluir.pdf'), nome_original='para-excluir.pdf')

    def url(self):
        return reverse('viagens_prestacoes:prestacao_documento_delete', args=[self.fixture.prestacao.pk, self.anexo.pk])

    def test_exclusao_leva_a_linha_e_o_arquivo(self):
        """O caminho feliz, escrito para sobreviver à mudança para `on_commit`.

        `captureOnCommitCallbacks(execute=True)` roda o que ficaria pendurado no commit —
        hoje não há nada pendurado e o teste passa igual; depois da fatia é ele que
        dispara a remoção do arquivo. A intenção não muda: o arquivo sai do disco.
        """
        from viagens_prestacoes.anexo_services import purgar_anexos_removidos
        caminho = Path(self.anexo.arquivo.path)
        self.assertTrue(caminho.exists())
        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.post(self.url())
        self.assertTrue(resposta.json()['ok'])
        self.assertFalse(PrestacaoDocumentoAnexo.objects.filter(pk=self.anexo.pk).exists())
        # m084: o arquivo fica guardado para o "Restaurar"; a limpeza o leva junto com a linha.
        self.assertTrue(caminho.exists())
        with self.captureOnCommitCallbacks(execute=True):
            purgar_anexos_removidos(dias=-1, apagar=True)
        self.assertFalse(caminho.exists(), 'arquivo órfão no storage')

    def test_falha_depois_de_apagar_devolve_a_linha_e_preserva_o_arquivo(self):
        """A garantia que esta fatia entrega. **Reprova hoje.**

        O que se quer não é "nunca sobrar arquivo órfão" — `on_commit` não promete isso, e
        prometer seria mentira: se o callback falhar depois do commit, a linha já foi. O
        que se quer é que **linha e arquivo nunca fiquem em desacordo perigoso**, isto é,
        a linha viva apontando para um arquivo destruído.

        A falha é injetada **depois** da exclusão, na marcação de status. Hoje, sem
        transação, quando ela estoura a linha já foi gravada como apagada e o arquivo já
        saiu do disco — e o usuário levou 500, então do ponto de vista dele a exclusão
        "não aconteceu", mas aconteceu. Com `atomic` + `on_commit`, a linha volta e o
        arquivo nunca chega a ser tocado, porque o callback só roda no commit que não
        houve.
        """
        caminho = Path(self.anexo.arquivo.path)

        def falhar(*args, **kwargs):
            raise RuntimeError('falha ao marcar o status depois de excluir')
        with mock.patch.object(PrestacaoServidor, 'save', falhar):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url())
        self.assertTrue(PrestacaoDocumentoAnexo.objects.filter(pk=self.anexo.pk).exists(), 'a operação falhou mas a linha ficou apagada')
        self.assertTrue(caminho.exists(), 'a operação falhou e o arquivo foi destruído: a linha voltaria apontando para um arquivo que não existe mais')
