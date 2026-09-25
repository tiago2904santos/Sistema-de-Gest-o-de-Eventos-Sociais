"""Uma ordem só para os documentos da prestação (`ORDEM_DOCUMENTOS_PRESTACAO`).

Ofício → despacho(s) → relatório técnico → diário de bordo → comprovante(s),
no pacote final E no "Baixar documentos" da lista — que antes punha o diário
antes do RT e levava um anexo só de cada tipo (dois comprovantes viravam um).
Comprovantes pela data da operação; o diário sempre em pé.
"""

from __future__ import annotations

from datetime import date
from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from core.leitura.pdf import ler_paginas
from core.leitura.pdf import rotacao_para_ficar_em_pe
from core.leitura.tests import fabrica as f

from .download_services import payload_downloads
from .models import ORDEM_DOCUMENTOS_PRESTACAO
from .models import PrestacaoDocumentoAnexo as Anexo
from .services import gerar_prestacao_consolidado_pdf
from .test_helpers import PrestacaoFixturesMixin
from .test_helpers import PrestacaoTestCase as TestCase
from .test_helpers import pdf_minimo


def _textos(pdf: bytes) -> list[str]:
    return [(p.extract_text() or "").strip() for p in PdfReader(BytesIO(pdf)).pages]


@override_settings(OCR_ATIVO=False)
class OrdemDoPacoteTests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=41)
        self.pc = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        self.ps.numero_solicitacao = "SOL-41"
        self.ps.save(update_fields=["numero_solicitacao"])

    def anexar(self, tipo, texto, *, individual=False, data=None, criado_em=None):
        anexo = Anexo.objects.create(
            prestacao=self.pc, servidor_prestacao=self.ps if individual else None, tipo=tipo,
            arquivo=SimpleUploadedFile(f"{texto}.pdf", pdf_minimo(texto)), nome_original=f"{texto}.pdf",
            data_operacao=data,
        )
        if criado_em:
            Anexo.objects.filter(pk=anexo.pk).update(criado_em=criado_em)
        return anexo

    def montar(self):
        agora = timezone.now()
        # Criados fora de ordem de propósito: a ordem de saída não é a de criação.
        self.anexar(Anexo.TIPO_COMPROVANTE, "COMPROVANTE-25", individual=True, data=date(2026, 9, 25), criado_em=agora - timedelta(hours=9))
        self.anexar(Anexo.TIPO_DB_ASSINADO, "DIARIO", criado_em=agora - timedelta(hours=8))
        self.anexar(Anexo.TIPO_COMPROVANTE, "COMPROVANTE-SEM-DATA", individual=True, criado_em=agora - timedelta(hours=7))
        self.anexar(Anexo.TIPO_RT_ASSINADO, "RELATORIO", individual=True, criado_em=agora - timedelta(hours=6))
        self.anexar(Anexo.TIPO_DESPACHO, "DESPACHO-1", criado_em=agora - timedelta(hours=5))
        self.anexar(Anexo.TIPO_COMPROVANTE, "COMPROVANTE-20", individual=True, data=date(2026, 9, 20), criado_em=agora - timedelta(hours=4))
        self.anexar(Anexo.TIPO_OFICIO_ASSINADO, "OFICIO", criado_em=agora - timedelta(hours=3))
        self.anexar(Anexo.TIPO_DESPACHO, "DESPACHO-2", criado_em=agora - timedelta(hours=2))

    ESPERADO = ["OFICIO", "DESPACHO-1", "DESPACHO-2", "RELATORIO", "DIARIO", "COMPROVANTE-20", "COMPROVANTE-25", "COMPROVANTE-SEM-DATA"]

    def test_constante_na_ordem_pedida(self):
        self.assertEqual(ORDEM_DOCUMENTOS_PRESTACAO, ("oficio_assinado", "despacho", "rt_assinado", "db_assinado", "comprovante"))

    def test_pacote_final_com_n_comprovantes(self):
        self.montar()
        self.assertEqual(_textos(gerar_prestacao_consolidado_pdf(self.ps)), self.ESPERADO)

    def test_baixar_pdf_unico_com_n_comprovantes(self):
        self.montar()
        self.assertEqual([item["id"] for item in payload_downloads(self.ps)["itens"]][:3], ["oficio", "despacho", "rt"])
        resposta = self.client.post(
            reverse("viagens_prestacoes:prestacao_baixar", args=[self.ps.pk]),
            {"itens": ["comprovante", "diario", "rt", "despacho", "oficio"], "formato": "pdf", "versao": "assinado", "saida": "unico"},
        )
        self.assertEqual(resposta.status_code, 200, resposta.content[:300])
        self.assertEqual(_textos(resposta.content), self.ESPERADO)

    def test_baixar_so_os_comprovantes_leva_todos(self):
        self.montar()
        resposta = self.client.post(
            reverse("viagens_prestacoes:prestacao_baixar", args=[self.ps.pk]),
            {"itens": ["comprovante"], "formato": "pdf", "versao": "assinado"},
        )
        self.assertEqual(_textos(resposta.content), ["COMPROVANTE-20", "COMPROVANTE-25", "COMPROVANTE-SEM-DATA"])

    def test_modal_da_lista_e_etapa_3_na_mesma_ordem(self):
        from .cartoes import cartao_da_lista

        cartao = cartao_da_lista(self.ps)
        self.assertEqual([a["key"] for a in cartao["anexos"]], ["oficio", "despacho", "rt", "diario", "comprovante"])
        etapa = self.client.get(reverse("viagens_prestacoes:documentos_servidor", args=[self.ps.pk]))
        self.assertEqual([u["id"] for u in etapa.context["uploads"]], ["oficio", "despacho", "rt", "diario", "comprovante"])

    def test_diario_antigo_sai_em_pe_no_pacote(self):
        """Anexo de antes da normalização (sem o cru): endireitado na saída, sem mexer no guardado."""
        deitado = f.girar_conteudo(f.diario_bordo(oficio="41/2026"), 90)
        self.anexar(Anexo.TIPO_OFICIO_ASSINADO, "OFICIO")
        self.anexar(Anexo.TIPO_DESPACHO, "DESPACHO")
        self.anexar(Anexo.TIPO_RT_ASSINADO, "RELATORIO", individual=True)
        self.anexar(Anexo.TIPO_COMPROVANTE, "COMPROVANTE", individual=True)
        Anexo.objects.create(prestacao=self.pc, tipo=Anexo.TIPO_DB_ASSINADO, arquivo=SimpleUploadedFile("diario.pdf", deitado), nome_original="diario.pdf")
        paginas = ler_paginas(gerar_prestacao_consolidado_pdf(self.ps))
        diario = paginas[3]
        self.assertTrue(diario.em_paisagem)
        self.assertEqual(rotacao_para_ficar_em_pe(diario), diario.rotacao)
