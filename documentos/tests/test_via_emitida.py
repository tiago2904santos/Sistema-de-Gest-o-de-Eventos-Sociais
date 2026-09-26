"""A via emitida (m113): o PDF que saiu se reimprime igual; mudar é nova versão."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from documentos.models import DocumentoArtefato
from documentos.services.emissao import registrar_emissao, via_emitida
from documentos.services.persistence import anexar_arquivo_assinado
from documentos.services.regeneracao import precisa_regerar
from documentos.services.types import DocumentoFormato, DocumentoTipo
from viagens_oficios.document_generation import gerar_documento, referencia_do_oficio
from viagens_oficios.models import Oficio
from viagens_oficios.tests.fixtures import CenarioOficioMixin


def _pdf(numero=1):
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n" + str(numero).encode() + b"\ntrailer<</Root 1 0 R>>\n%%EOF\n")


class ViaEmitidaTests(CenarioOficioMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.oficio = self.criar()

    def _via(self):
        return via_emitida(DocumentoTipo.OFICIO, reference=referencia_do_oficio(self.oficio), oficio_id=self.oficio.pk)

    def test_primeira_geracao_vira_a_versao_1_e_os_pedidos_seguintes_a_devolvem(self):
        primeiro = gerar_documento(self.oficio, DocumentoFormato.PDF)
        via = self._via()
        self.assertIsNotNone(via)
        self.assertEqual(via.versao_emitida, 1)
        self.assertEqual(via.pk, primeiro.artefato_id)
        self.assertIsNotNone(via.emitida_em)
        # O ofício mudou depois de emitido: o PDF continua o que saiu.
        Oficio.objects.filter(pk=self.oficio.pk).update(motivo="OUTRO MOTIVO, DEPOIS DA EMISSÃO")
        self.oficio.refresh_from_db()
        segundo = gerar_documento(self.oficio, DocumentoFormato.PDF)
        self.assertEqual(segundo.hash_sha256, primeiro.hash_sha256)
        self.assertEqual(segundo.artefato_id, primeiro.artefato_id)
        self.assertTrue(segundo.cache_hit)
        self.assertEqual(self._via().versao_emitida, 1)

    def test_nova_versao_refaz_com_os_dados_de_hoje_e_numera_a_seguinte(self):
        primeiro = gerar_documento(self.oficio, DocumentoFormato.PDF)
        # Sem mudança, "nova versão" não gasta número.
        igual = gerar_documento(self.oficio, DocumentoFormato.PDF, nova_versao=True)
        self.assertEqual(igual.hash_sha256, primeiro.hash_sha256)
        self.assertEqual(self._via().versao_emitida, 1)
        Oficio.objects.filter(pk=self.oficio.pk).update(motivo="OUTRO MOTIVO, DEPOIS DA EMISSÃO")
        self.oficio.refresh_from_db()
        segundo = gerar_documento(self.oficio, DocumentoFormato.PDF, nova_versao=True)
        self.assertNotEqual(segundo.hash_sha256, primeiro.hash_sha256)
        via = self._via()
        self.assertEqual(via.versao_emitida, 2)
        self.assertEqual(via.pk, segundo.artefato_id)
        # A versão 1 continua guardada, e daqui em diante volta a 2.
        self.assertEqual(DocumentoArtefato.objects.filter(oficio=self.oficio, versao_emitida=1).count(), 1)
        self.assertEqual(gerar_documento(self.oficio, DocumentoFormato.PDF).hash_sha256, segundo.hash_sha256)

    def test_docx_nao_e_via(self):
        gerar_documento(self.oficio, DocumentoFormato.DOCX)
        self.assertIsNone(self._via())
        self.assertFalse(DocumentoArtefato.objects.filter(oficio=self.oficio, versao_emitida__isnull=False).exists())

    def test_a_via_assinada_vale_por_cima_da_emitida(self):
        gerar_documento(self.oficio, DocumentoFormato.PDF)
        via = self._via()
        anexar_arquivo_assinado(via, SimpleUploadedFile("assinado.pdf", _pdf(7), "application/pdf"))
        self.assertEqual(gerar_documento(self.oficio, DocumentoFormato.PDF).conteudo, _pdf(7))
        self.assertNotEqual(gerar_documento(self.oficio, DocumentoFormato.PDF, usar_assinado=False).conteudo, _pdf(7))

    def test_a_via_nunca_e_refeita_no_download(self):
        gerar_documento(self.oficio, DocumentoFormato.PDF)
        via = self._via()
        DocumentoArtefato.objects.filter(pk=via.pk).update(engine="word_com")
        via.refresh_from_db()
        self.assertFalse(precisa_regerar(via, assinado=False))

    def test_registrar_emissao_sem_via_e_a_versao_1_e_a_mesma_via_nao_repete(self):
        gerado = gerar_documento(self.oficio, DocumentoFormato.PDF)
        artefato = DocumentoArtefato.objects.get(pk=gerado.artefato_id)
        self.assertEqual(registrar_emissao(artefato, reference=referencia_do_oficio(self.oficio)).versao_emitida, 1)
        self.assertEqual(registrar_emissao(artefato, reference=referencia_do_oficio(self.oficio), nova_versao=True).versao_emitida, 1)

    def test_o_botao_emitir_nova_versao_manda_nova_versao_1(self):
        gerar_documento(self.oficio, DocumentoFormato.PDF)
        Oficio.objects.filter(pk=self.oficio.pk).update(motivo="OUTRO MOTIVO, DEPOIS DA EMISSÃO")
        url = reverse("viagens_oficios:gerar", args=[self.oficio.pk, "oficio", "pdf"])
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self._via().versao_emitida, 1)
        self.assertEqual(self.client.post(url, {"nova_versao": "1"}).status_code, 200)
        self.assertEqual(self._via().versao_emitida, 2)
        tela = self.client.get(reverse("viagens_oficios:editar", args=[self.oficio.pk]))
        self.assertContains(tela, "Versão 2 emitida em")
        self.assertContains(tela, "Emitir nova versão")
