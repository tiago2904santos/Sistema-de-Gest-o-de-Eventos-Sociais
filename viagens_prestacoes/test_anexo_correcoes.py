"""Correções de anexo que vieram junto com o importador de processo.

- `CarimboError` de ofício escaneado ou "embrulhado" pelo eProtocolo não recusa
  mais o upload inteiro (era 422 e nada anexado): o ofício entra e o servidor
  vai para "Ajustar posição" — e nunca é carimbado no lugar errado (lacuna L2);
- o diário de bordo anexado à mão sai em pé (paisagem), guardando o cru;
- o modal de anexar da lista aceita imagem quando a opção é o comprovante;
- o cartão da Etapa 3 mostra o motivo real da recusa (`message`/`errors` do
  autosave, `error` das rotas de anexar).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from core.leitura.pdf import ler_paginas
from core.leitura.pdf import rotacao_para_ficar_em_pe
from core.leitura.tests import fabrica as f

from .cartoes import cartao_da_lista
from .models import PrestacaoDocumentoAnexo as Anexo
from .test_carimbo import pdf_do_oficio
from .test_helpers import PrestacaoFixturesMixin
from .test_helpers import PrestacaoTestCase as TestCase
from .test_helpers import imagem_bytes


def _bytes(campo) -> bytes:
    campo.open("rb")
    try:
        return campo.read()
    finally:
        campo.close()


@override_settings(OCR_ATIVO=False)
class CarimboNaoRecusaTests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=61, servidores=(self.criar_servidor("Joao Da Silva"),))
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        self.ps.numero_solicitacao = "2026001234"
        self.ps.save(update_fields=["numero_solicitacao"])
        self.referencia = pdf_do_oficio([("Joao Da Silva", "2026001234")])

    def _anexar(self, pdf):
        with mock.patch("viagens_prestacoes.services.gerar_oficio_prestacao_pdf", return_value=self.referencia):
            return self.client.post(
                reverse("viagens_prestacoes:prestacao_oficio_assinado_anexar", args=[self.prestacao.pk]),
                {"arquivo": SimpleUploadedFile("oficio.pdf", pdf, content_type="application/pdf")},
            )

    def _mensagens(self, resposta):
        return " ".join(str(m) for m in get_messages(resposta.wsgi_request))

    def test_oficio_escaneado_entra_e_manda_ajustar(self):
        resposta = self._anexar(f.pagina_imagem(["Ofício 61/2026", "Joao Da Silva"]))
        self.assertEqual(resposta.status_code, 302)
        anexo = self.prestacao.documentos_anexos.get(tipo=Anexo.TIPO_OFICIO_ASSINADO)
        self.assertFalse(anexo.carimbos.exists())
        self.assertIn("Ajustar posição", self._mensagens(resposta))

    def test_oficio_embrulhado_nao_e_carimbado_no_lugar_errado(self):
        embrulhado = f.emoldurar(pdf_do_oficio([("Joao Da Silva", "")], com_numero=False), fls="2", mov="2", embrulhar=True)
        resposta = self._anexar(embrulhado)
        self.assertEqual(resposta.status_code, 302)
        anexo = self.prestacao.documentos_anexos.get(tipo=Anexo.TIPO_OFICIO_ASSINADO)
        self.assertFalse(anexo.carimbos.exists())
        self.assertIn("Ajustar posição", self._mensagens(resposta))

    def test_oficio_com_texto_continua_carimbado(self):
        resposta = self._anexar(pdf_do_oficio([("Joao Da Silva", "")], deslocamento=40, com_numero=False))
        self.assertEqual(resposta.status_code, 302)
        anexo = self.prestacao.documentos_anexos.get(tipo=Anexo.TIPO_OFICIO_ASSINADO)
        self.assertEqual(anexo.carimbos.count(), 1)


@override_settings(OCR_ATIVO=False)
class DiarioAnexadoAMaoTests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=62)
        self.ps = self.fixture.prestacoes_servidor[0]

    def _anexar(self, pdf):
        return self.client.post(
            reverse("viagens_prestacoes:prestacao_servidor_assinado_anexar", args=[self.ps.pk, Anexo.TIPO_DB_ASSINADO]),
            {"arquivo": SimpleUploadedFile("diario.pdf", pdf, content_type="application/pdf")},
        )

    def test_diario_deitado_fica_em_pe_e_guarda_o_cru(self):
        for giro in (90, 270):
            with self.subTest(giro=giro):
                self._anexar(f.girar_conteudo(f.diario_bordo(oficio="62/2026"), giro))
                anexo = self.fixture.prestacao.documentos_anexos.get(tipo=Anexo.TIPO_DB_ASSINADO)
                pagina = ler_paginas(_bytes(anexo.arquivo))[0]
                self.assertTrue(pagina.em_paisagem)
                self.assertEqual(rotacao_para_ficar_em_pe(pagina), pagina.rotacao)
                self.assertTrue(anexo.arquivo_original)
                self.assertEqual(ler_paginas(_bytes(anexo.arquivo_original))[0].rotacao, 0)

    def test_diario_em_pe_nao_e_reescrito(self):
        self._anexar(f.diario_bordo(oficio="62/2026"))
        anexo = self.fixture.prestacao.documentos_anexos.get(tipo=Anexo.TIPO_DB_ASSINADO)
        self.assertFalse(anexo.arquivo_original)
        self.assertEqual(ler_paginas(_bytes(anexo.arquivo))[0].rotacao, 0)

    def test_falha_ao_endireitar_nao_deixa_arquivo_girado_orfao(self):
        raiz = Path(settings.MEDIA_ROOT)
        antes = {p for p in raiz.rglob("*") if p.is_file()}
        salvar = Anexo.save

        def falha_ao_gravar_o_giro(anexo, *args, **kwargs):
            if "arquivo_original" in (kwargs.get("update_fields") or []):
                raise RuntimeError("falha ao gravar o giro")
            return salvar(anexo, *args, **kwargs)

        with mock.patch.object(Anexo, "save", falha_ao_gravar_o_giro):
            with self.assertRaises(RuntimeError):
                self._anexar(f.girar_conteudo(f.diario_bordo(oficio="62/2026"), 90))
        self.assertFalse(self.fixture.prestacao.documentos_anexos.exists())
        self.assertEqual({p for p in raiz.rglob("*") if p.is_file()}, antes)


class ModalEEtapa3Tests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=63)
        self.ps = self.fixture.prestacoes_servidor[0]

    def test_modal_da_lista_aceita_imagem_so_no_comprovante(self):
        opcoes = json.loads(cartao_da_lista(self.ps)["opcoes_anexar"])
        com_imagem = [o["nome"] for o in opcoes if o.get("imagem")]
        self.assertEqual(com_imagem, ["Comprovante"])
        js = (Path(settings.BASE_DIR) / "static/js/anexar-assinado.js").read_text(encoding="utf-8")
        self.assertIn("alvo.imagem", js)
        self.assertIn("image/png", js)

    def test_comprovante_em_foto_e_aceito(self):
        resposta = self.client.post(
            reverse("viagens_prestacoes:prestacao_servidor_assinado_anexar", args=[self.ps.pk, Anexo.TIPO_COMPROVANTE]),
            {"arquivo": SimpleUploadedFile("comprovante.png", imagem_bytes(), content_type="image/png")},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(self.ps.documentos_anexos.filter(tipo=Anexo.TIPO_COMPROVANTE).exists())

    def test_recusa_da_etapa_3_traz_o_motivo_nas_chaves_que_o_js_le(self):
        """O cartão da Etapa 3 fala com dois endpoints; cada um responde de um jeito."""
        xhr = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
        falso = SimpleUploadedFile("falso.pdf", b"nao sou pdf", content_type="application/pdf")
        # Comprovante (autosave, vários arquivos): `message` genérica + `errors` com o motivo.
        autosave = self.client.post(
            reverse("viagens_prestacoes:prestacao_servidor_arquivo_autosave", args=[self.ps.pk]),
            {f"ps-{self.ps.pk}-comprovante_arquivos": falso}, **xhr,
        )
        self.assertEqual(autosave.status_code, 400)
        corpo = autosave.json()
        self.assertTrue(corpo["message"])
        self.assertIn("PDF", " ".join(sum(corpo["errors"].values(), [])))
        # RT (rota de anexar): `error` e `message`.
        falso.seek(0)
        anexar = self.client.post(
            reverse("viagens_prestacoes:prestacao_servidor_assinado_anexar", args=[self.ps.pk, Anexo.TIPO_RT_ASSINADO]),
            {"arquivo": SimpleUploadedFile("falso.pdf", b"nao sou pdf", content_type="application/pdf")}, **xhr,
        )
        self.assertEqual(anexar.status_code, 400)
        self.assertEqual(anexar.json()["error"], anexar.json()["message"])
        js = (Path(settings.BASE_DIR) / "static/js/viagens-prestacoes.js").read_text(encoding="utf-8")
        leitor = js[js.index("function motivoDaRecusa"):js.index("/* ---------- anexar direto do cartão")]
        for chave in ("dados.errors", "dados.error", "dados.message"):
            self.assertIn(chave, leitor)
        self.assertIn("motivoDaRecusa(res.dados)", js)
