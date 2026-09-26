"""A via emitida e a assinada da OS, do ofício e do certifico (m045)."""

import datetime as dt
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from documentos.models import DocumentoArtefato

from . import documentos, vias
from .editor import TipoCoffee
from .models import HistoricoCoffeeBreak
from .tests import EtapasBase, _pdf_em_branco


def _gerado(html):
    """O PDF "gerado" dos testes (sem depender do WeasyPrint)."""
    return _pdf_em_branco()


ASSINADO = _pdf_em_branco(2)


@mock.patch.object(documentos, "_pdf_do_html", side_effect=_gerado)
class ViasDaOSTests(EtapasBase):
    def test_emitir_guarda_a_via_com_quem_emitiu_e_nao_repete_a_mesma_folha(self, _pdf):
        resposta = self.client.get(reverse("coffee_break:ordem_servico", args=[self.solicitacao.pk]))
        self.assertEqual(resposta.status_code, 200)
        via = DocumentoArtefato.objects.get(coffee_break_solicitacao=self.solicitacao)
        self.assertEqual(via.tipo, TipoCoffee.ORDEM_SERVICO.value)
        self.assertEqual(via.criado_por, self.ascom)
        self.client.get(reverse("coffee_break:ordem_servico", args=[self.solicitacao.pk]) + "?baixar=1")
        self.assertEqual(DocumentoArtefato.objects.filter(coffee_break_solicitacao=self.solicitacao).count(), 1)
        self.assertEqual(_pdf.call_count, 1)
        # A folha mudou (outro local de entrega): outra via.
        self.solicitacao.local_entrega = "2DP"
        self.solicitacao.save()
        documentos.ordem_servico_pdf(self.solicitacao)
        self.assertEqual(DocumentoArtefato.objects.filter(coffee_break_solicitacao=self.solicitacao).count(), 2)

    def test_assinada_vale_no_lugar_da_gerada_ate_ser_removida(self, _pdf):
        url = reverse("coffee_break:anexar_assinado", args=[self.solicitacao.pk, "os"])
        resposta = self.client.post(url, {"arquivo": SimpleUploadedFile("os-assinada.pdf", ASSINADO, "application/pdf")})
        self.assertRedirects(resposta, reverse("coffee_break:editar", args=[self.solicitacao.pk]))
        # Sem via emitida antes, a gerada na hora recebeu a assinada.
        self.assertIsNotNone(vias.assinada(TipoCoffee.ORDEM_SERVICO, self.solicitacao))
        self.assertEqual(documentos.ordem_servico_pdf(self.solicitacao), ASSINADO)
        self.assertEqual(self.client.get(reverse("coffee_break:ordem_servico", args=[self.solicitacao.pk])).content, ASSINADO)
        self.assertEqual(documentos.parte_pdf(self.solicitacao, "os")[:4], b"%PDF")
        self.assertTrue(
            HistoricoCoffeeBreak.objects.filter(solicitacao=self.solicitacao, descricao__contains="Via assinada da ordem de serviço anexada").exists()
        )
        tela = self.client.get(reverse("coffee_break:editar", args=[self.solicitacao.pk]))
        self.assertContains(tela, "Vale a via assinada")
        self.assertContains(tela, "Trocar assinado")

        self.client.post(url, {"acao": "remover"})
        self.assertIsNone(vias.assinada(TipoCoffee.ORDEM_SERVICO, self.solicitacao))
        self.assertNotEqual(documentos.ordem_servico_pdf(self.solicitacao), ASSINADO)
        # A assinada removida continua guardada (revogada), com o arquivo.
        via = vias.ultima_via(TipoCoffee.ORDEM_SERVICO, self.solicitacao)
        versao = via.versoes_assinadas.get()
        self.assertIsNotNone(versao.revogada_em)
        baixada = self.client.get(reverse("coffee_break:via_arquivo", args=[via.pk]) + f"?assinada={versao.pk}")
        self.assertEqual(b"".join(baixada.streaming_content), ASSINADO)

    def test_cancelada_nao_recebe_assinada(self, _pdf):
        self.solicitacao.cancelada = True
        self.solicitacao.save()
        url = reverse("coffee_break:anexar_assinado", args=[self.solicitacao.pk, "os"])
        self.client.post(url, {"arquivo": SimpleUploadedFile("os.pdf", ASSINADO, "application/pdf")})
        self.assertFalse(DocumentoArtefato.objects.filter(coffee_break_solicitacao=self.solicitacao).exists())

    def test_arquivo_que_nao_e_pdf_e_recusado(self, _pdf):
        url = reverse("coffee_break:anexar_assinado", args=[self.solicitacao.pk, "os"])
        resposta = self.client.post(url, {"arquivo": SimpleUploadedFile("os.pdf", b"nada", "application/pdf")}, follow=True)
        self.assertContains(resposta, "não parece ser um PDF")
        self.assertIsNone(vias.assinada(TipoCoffee.ORDEM_SERVICO, self.solicitacao))

    def test_documento_desconhecido(self, _pdf):
        url = reverse("coffee_break:anexar_assinado", args=[self.solicitacao.pk, "contrato"])
        self.assertEqual(self.client.post(url).status_code, 404)


@mock.patch.object(documentos, "_pdf_do_html", side_effect=_gerado)
class ViasDoPagamentoTests(EtapasBase):
    def test_oficio_assinado_mora_na_principal_e_vale_para_todo_o_pagamento(self, _pdf):
        self._completar_para_protocolo(self.solicitacao)
        outra = self.criar_solicitacao(
            numero="42/2026", descricao_evento="Outro evento", local_entrega="3DP", responsavel_recebimento="Bia",
            numero_nota_fiscal="8958", numero_oficio="124/2026", pagamento_com=self.solicitacao, data_inicio_evento=dt.date(2026, 8, 20),
        )
        url = reverse("coffee_break:anexar_assinado", args=[outra.pk, "oficio"])
        self.client.post(url, {"arquivo": SimpleUploadedFile("oficio.pdf", ASSINADO, "application/pdf")})
        via = DocumentoArtefato.objects.get(tipo=TipoCoffee.OFICIO.value)
        self.assertEqual(via.coffee_break_solicitacao, self.solicitacao)
        self.assertEqual(documentos.oficio_pdf(self.solicitacao), ASSINADO)
        self.assertEqual(documentos.oficio_pdf(outra), ASSINADO)
        self.assertEqual(documentos.parte_pdf(self.solicitacao, "oficio")[:4], b"%PDF")

    def test_certifico_assinado_na_etapa_da_nota(self, _pdf):
        self._completar_para_protocolo(self.solicitacao)
        url = reverse("coffee_break:anexar_assinado", args=[self.solicitacao.pk, "certifico"])
        resposta = self.client.post(url, {"arquivo": SimpleUploadedFile("certifico.pdf", ASSINADO, "application/pdf")})
        self.assertRedirects(resposta, reverse("coffee_break:etapa_nota", args=[self.solicitacao.pk]))
        self.assertEqual(documentos.certifico_pdf(self.solicitacao), ASSINADO)
        tela = self.client.get(reverse("coffee_break:etapa_nota", args=[self.solicitacao.pk]))
        self.assertContains(tela, reverse("coffee_break:anexar_assinado", args=[self.solicitacao.pk, "oficio"]))
        self.assertContains(tela, "vias guardadas")
