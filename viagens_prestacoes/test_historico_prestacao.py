"""m104: o histórico da prestação (anexos, finalização, datas e números) aparece na Etapa 3."""
from django.core.files.base import ContentFile
from django.urls import reverse

from .document_views import historico_da_prestacao
from .models import PrestacaoDocumentoAnexo
from .test_helpers import PDF_MINIMO, PrestacaoFixturesMixin, PrestacaoTestCase as TestCase


class HistoricoDaPrestacaoTests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        self.setUpPrestacaoFixtures()
        with self.captureOnCommitCallbacks(execute=True):
            self.fixture = self.criar_prestacao(numero=104)
        self.ps = self.fixture.prestacoes_servidor[0]
        self.prestacao = self.fixture.prestacao

    def test_trilha_reune_a_prestacao_os_servidores_e_os_anexos(self):
        with self.captureOnCommitCallbacks(execute=True):
            anexo = PrestacaoDocumentoAnexo.objects.create(
                prestacao=self.prestacao, servidor_prestacao=self.ps, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE,
                arquivo=ContentFile(PDF_MINIMO, name="comprovante.pdf"), nome_original="comprovante.pdf",
            )
            self.ps.numero_solicitacao = "2026/123"
            self.ps.save(update_fields=["numero_solicitacao", "atualizado_em"])
            anexo.delete()
        itens = historico_da_prestacao(self.prestacao)
        sobre = [(i["sobre"], i["acao"]) for i in itens]
        self.assertIn(("Documento comprovante.pdf", "Exclusão"), sobre)
        self.assertIn(("Documento comprovante.pdf", "Criação"), sobre)
        edicao = next(i for i in itens if i["sobre"].startswith("Servidor") and i["mudancas"])
        self.assertEqual([(m["antes"], m["depois"]) for m in edicao["mudancas"]], [("—", "2026/123")])
        # A criação da prestação e a do servidor também estão lá.
        self.assertIn(("Prestação de Contas", "Criação"), sobre)

    def test_etapa_3_mostra_o_bloco_de_historico(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.ps.definir_finalizada(True, justificativa="")
        resposta = self.client.get(reverse("viagens_prestacoes:documentos_servidor", args=[self.ps.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Histórico de alterações")
        conteudo = resposta.content.decode()
        self.assertIn('id="historico"', conteudo)
        self.assertIn("Finalizada", conteudo)
        self.assertTrue(any(i["sobre"].startswith("Servidor") for i in resposta.context["historico"]))
