"""Conferência do PDF assinado ao anexar (m112): assinatura digital (campo
/Sig ou carimbo), quem assinou e quando, e se o PDF é do documento certo
(número, protocolo, nome). É aviso, não bloqueio; o que se leu fica na versão."""
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from pypdf import PdfWriter
from pypdf.generic import (ArrayObject, ByteStringObject, DictionaryObject, NameObject, NumberObject, StreamObject,
                           TextStringObject)

from documentos.models import DocumentoArtefato, DocumentoAssinaturaVersao
from documentos.services.conferencia_assinado import conferir_pdf_assinado
from documentos.services.persistence import anexar_arquivo_assinado
from viagens_oficios.tests.fixtures import CenarioOficioMixin


def pdf_de_teste(texto, *, assinante=None, quando="D:20260924103000-03'00'", so_certificado=False):
    """Um PDF de uma página com `texto` e, com `assinante`, um campo de
    assinatura preenchido (o nome no /Name ou, `so_certificado`, só no CN do
    certificado dentro do /Contents, como a ICP-Brasil grava)."""
    escritor = PdfWriter()
    pagina = escritor.add_blank_page(width=595, height=842)
    fonte = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                              NameObject("/BaseFont"): NameObject("/Helvetica")})
    pagina[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): fonte})})
    conteudo = StreamObject()
    conteudo.set_data(f"BT /F1 12 Tf 72 760 Td ({texto}) Tj ET".encode("latin-1"))
    pagina[NameObject("/Contents")] = escritor._add_object(conteudo)
    if assinante:
        nome_cn = f"{assinante.upper()}:12345678901".encode("utf-8")
        contents = b"\x30\x82\x01\x00" + b"\x06\x03\x55\x04\x03\x0c" + bytes([len(b"AC Teste v5")]) + b"AC Teste v5" \
            + b"\x06\x03\x55\x04\x03\x0c" + bytes([len(nome_cn)]) + nome_cn
        valor = DictionaryObject({
            NameObject("/Type"): NameObject("/Sig"), NameObject("/Filter"): NameObject("/Adobe.PPKLite"),
            NameObject("/M"): TextStringObject(quando), NameObject("/Contents"): ByteStringObject(contents),
            NameObject("/ByteRange"): ArrayObject([NumberObject(0), NumberObject(1), NumberObject(2), NumberObject(3)]),
        })
        if not so_certificado:
            valor[NameObject("/Name")] = TextStringObject(assinante)
        campo = DictionaryObject({
            NameObject("/FT"): NameObject("/Sig"), NameObject("/T"): TextStringObject("Assinatura1"),
            NameObject("/V"): escritor._add_object(valor), NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"), NameObject("/Rect"): ArrayObject([NumberObject(0)] * 4),
            NameObject("/P"): pagina.indirect_reference,
        })
        ref = escritor._add_object(campo)
        pagina[NameObject("/Annots")] = ArrayObject([ref])
        escritor._root_object[NameObject("/AcroForm")] = DictionaryObject({
            NameObject("/Fields"): ArrayObject([ref]), NameObject("/SigFlags"): NumberObject(3),
        })
    saida = BytesIO()
    escritor.write(saida)
    return saida.getvalue()


class ConferenciaDoPdfTests(TestCase):
    def test_pdf_sem_assinatura_e_com_numero_errado(self):
        c = conferir_pdf_assinado(pdf_de_teste("Oficio No 123/2026 Protocolo 12.345.678-9"),
                                  numero="125/2026", protocolo="123456789", nomes=["ANA TESTE"], rotulo="ofício")
        self.assertFalse(c.assinado)
        self.assertIn("não tem assinatura digital", c.resumo())
        self.assertIn("O número neste PDF é 123/2026, mas você está anexando no ofício 125/2026.", c.avisos)
        self.assertIn("O nome ANA TESTE não aparece neste PDF.", c.avisos)
        self.assertFalse(any("protocolo" in a for a in c.avisos))

    def test_campo_de_assinatura_da_o_nome_e_a_data(self):
        c = conferir_pdf_assinado(pdf_de_teste("Oficio No 123/2026 ANA TESTE", assinante="Fulano de Tal"),
                                  numero="123/2026", nomes=["Ana Teste"])
        self.assertTrue(c.assinado)
        self.assertEqual(c.assinante.nome, "Fulano de Tal")
        self.assertEqual(c.resumo(), "Assinado digitalmente por Fulano de Tal em 24/09/2026 10:30.")
        self.assertEqual(c.avisos, [])

    def test_nome_so_no_certificado_icp(self):
        c = conferir_pdf_assinado(pdf_de_teste("Oficio No 123/2026", assinante="Fulano de Tal", so_certificado=True))
        self.assertTrue(c.assinado)
        self.assertEqual(c.assinante.nome, "FULANO DE TAL")
        self.assertEqual(c.assinante.origem, "certificado")

    def test_carimbo_do_eprotocolo_e_da_icp_no_texto(self):
        texto = "Assinatura Qualificada realizada por: Beltrano Silva em 20/09/2026 09:15. Inserido ao protocolo 12.345.678-9"
        c = conferir_pdf_assinado(pdf_de_teste(texto))
        self.assertTrue(c.assinado)
        self.assertEqual(c.assinante.nome, "Beltrano Silva")
        c = conferir_pdf_assinado(pdf_de_teste("Assinado de forma digital por CICRANO SOUZA:12345678901 Dados: 2026.09.22 14:05"))
        self.assertTrue(c.assinado)
        self.assertEqual(c.assinante.nome, "CICRANO SOUZA")

    def test_protocolo_diferente_e_avisado(self):
        c = conferir_pdf_assinado(pdf_de_teste("Protocolo 22.222.222-2"), protocolo="12.345.678-9", rotulo="ofício")
        self.assertIn("O protocolo neste PDF é 22.222.222-2, mas o ofício é do protocolo 12.345.678-9.", c.avisos)


class AnexarComConferenciaTests(CenarioOficioMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.oficio = self.criar()
        self.artefato = DocumentoArtefato.objects.create(tipo="oficio", formato="pdf", oficio=self.oficio, hash_sha256="0" * 64,
                                                         nome_exibicao="oficio_1-2026_x.pdf", arquivo=ContentFile(b"%PDF-1.4", name="o.pdf"))

    def test_o_que_se_leu_fica_na_versao_e_volta_no_artefato(self):
        pdf = pdf_de_teste(f"Oficio No {self.oficio.numero_formatado}", assinante="Fulano de Tal")
        anexar_arquivo_assinado(self.artefato, SimpleUploadedFile("a.pdf", pdf, content_type="application/pdf"))
        versao = DocumentoAssinaturaVersao.objects.get(artefato=self.artefato)
        self.assertEqual(versao.assinante_nome, "Fulano de Tal")
        self.assertEqual(versao.assinado_em_digital.year, 2026)
        self.assertTrue(versao.conferencia["assinado"])
        self.assertTrue(self.artefato.conferencia_assinado.assinado)

    def test_a_tela_avisa_sem_bloquear(self):
        url = reverse("viagens_oficios:assinatura_artefato", args=[self.artefato.pk])
        pdf = pdf_de_teste("Oficio No 999/2026")
        r = self.client.post(url, {"arquivo": SimpleUploadedFile("a.pdf", pdf, content_type="application/pdf"),
                                   "next": reverse("viagens_oficios:editar", args=[self.oficio.pk])}, follow=True)
        textos = [str(m) for m in r.context["messages"]]
        self.assertTrue(any("anexado" in t for t in textos), textos)
        self.assertTrue(any("não tem assinatura digital" in t for t in textos), textos)
        self.assertTrue(any(f"O número neste PDF é 999/2026, mas você está anexando no ofício 001/2026" in t for t in textos), textos)
        self.assertTrue(DocumentoAssinaturaVersao.objects.filter(artefato=self.artefato).exists())

    def test_previa_do_modal(self):
        url = reverse("documentos:conferir_assinado", args=[self.artefato.pk])
        pdf = pdf_de_teste(f"Oficio No {self.oficio.numero_formatado}", assinante="Fulano de Tal")
        r = self.client.post(url, {"arquivo": SimpleUploadedFile("a.pdf", pdf, content_type="application/pdf")})
        self.assertEqual(r.status_code, 200)
        dados = r.json()
        self.assertTrue(dados["ok"] and dados["assinado"])
        self.assertIn("Fulano de Tal", dados["resumo"])
        self.assertEqual(dados["avisos"], [])
        self.assertFalse(DocumentoAssinaturaVersao.objects.exists())
        r = self.client.post(url, {"arquivo": SimpleUploadedFile("a.txt", b"nada", content_type="text/plain")})
        self.assertEqual(r.status_code, 400)
