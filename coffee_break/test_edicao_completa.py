"""Edição completa da OS, do ofício e do certifico do Coffee Break (m057): a
versão editada vale no PDF (via emitida, e-mail, protocolo), com o ofício do
pagamento guardado na OS principal; a via assinada trava a edição."""

import datetime as dt
import json
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from documentos.models import DocumentoVersaoEditada, ModeloTextoDocumento

from . import documentos
from .editor import TipoCoffee
from .tests import EtapasBase, _pdf_em_branco


def _url(nome, tipo, pk):
    return reverse(f"documentos:{nome}", args=[tipo.value, pk])


@mock.patch.object(documentos, "_pdf_do_html", side_effect=lambda html: _pdf_em_branco())
class EdicaoCompletaCoffeeTests(EtapasBase):
    def salvar(self, tipo, pk, corpo, estado=""):
        return self.client.post(_url("editor_completo_salvar", tipo, pk),
                                data=json.dumps({"estado": estado, "regioes": {"corpo": corpo}}), content_type="application/json")

    def test_os_editada_por_inteiro_sai_no_pdf(self, _pdf):
        s = self.solicitacao
        self.assertEqual(self.client.get(_url("editor_completo", TipoCoffee.ORDEM_SERVICO, s.pk)).status_code, 200)
        folha = self.client.get(_url("editor_completo_folha", TipoCoffee.ORDEM_SERVICO, s.pk)).content.decode()
        self.assertIn("<!--ed:corpo-->", folha)
        self.assertIn("<!--ed:cabecalho-->", folha)
        r = self.salvar(TipoCoffee.ORDEM_SERVICO, s.pk, "<p>OS reescrita <b>à mão</b></p><script>x</script>")
        self.assertEqual(r.status_code, 200, r.content)
        documentos.ordem_servico_pdf(s)
        html = _pdf.call_args.args[0]
        self.assertIn("OS reescrita <b>à mão</b>", html)
        self.assertNotIn("<script>x", html)
        self.assertIn("timbre-cabecalho", html)  # o timbre continua o do modelo
        # A prévia da tela e a folha do editor de campos mostram a versão editada.
        self.assertIn("OS reescrita", documentos.ordem_servico_previa(s))
        self.assertIn("OS reescrita", self.client.get(reverse("documentos:editor_folha", args=[TipoCoffee.ORDEM_SERVICO.value, s.pk])).content.decode())

    def test_oficio_do_pagamento_fica_na_os_principal(self, _pdf):
        self._completar_para_protocolo(self.solicitacao)
        outra = self.criar_solicitacao(
            numero="42/2026", descricao_evento="Outro evento", local_entrega="3DP", responsavel_recebimento="Bia",
            numero_nota_fiscal="8958", numero_oficio="124/2026", pagamento_com=self.solicitacao, data_inicio_evento=dt.date(2026, 8, 20),
        )
        r = self.salvar(TipoCoffee.OFICIO, outra.pk, "<p>Ofício do pagamento editado</p>")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(DocumentoVersaoEditada.objects.get().coffee_break_solicitacao, self.solicitacao)
        documentos.oficio_pdf(self.solicitacao)
        self.assertIn("Ofício do pagamento editado", _pdf.call_args.args[0])

    def test_via_assinada_trava_a_edicao(self, _pdf):
        s = self.solicitacao
        self.client.post(reverse("coffee_break:anexar_assinado", args=[s.pk, "os"]),
                         {"arquivo": SimpleUploadedFile("os.pdf", _pdf_em_branco(2), "application/pdf")})
        r = self.salvar(TipoCoffee.ORDEM_SERVICO, s.pk, "<p>x</p>")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(DocumentoVersaoEditada.objects.exists())

    def test_texto_do_modelo_do_certifico(self, _pdf):
        self._completar_para_protocolo(self.solicitacao)
        url = reverse("documentos:modelos_tipo", args=[TipoCoffee.CERTIFICO.value])
        # Quem só opera o módulo não mexe no modelo; a administração, sim.
        self.assertEqual(self.client.post(url, {"texto__cb_titulo": "X"}).status_code, 403)
        self.client.force_login(self.admin_modulo)
        self.assertEqual(self.client.get(url).status_code, 200)
        resposta = self.client.post(url, {"texto__cb_titulo": "CERTIFICO DE ENTREGA"})
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(ModeloTextoDocumento.objects.filter(tipo_documento=TipoCoffee.CERTIFICO.value, chave="cb_titulo").exists())
        documentos.certifico_pdf(self.solicitacao)
        self.assertIn("CERTIFICO DE ENTREGA", _pdf.call_args.args[0])
