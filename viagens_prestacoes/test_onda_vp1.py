"""Onda V-P1 da prestação de contas (m080–m094): regressões de cada item."""

from __future__ import annotations

import io
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse

from .carimbo_services import ler_fragmentos
from .models import PrestacaoDocumentoAnexo as Anexo
from .solicitacao_services import salvar_solicitacao_do_autosave
from .test_carimbo import pdf_do_oficio
from .test_helpers import PrestacaoFixturesMixin
from .test_helpers import PrestacaoTestCase
from .test_helpers import pdf_minimo


def _foto_deitada_com_exif_em_pe() -> bytes:
    """JPG 400×300 (deitado no sensor) com a etiqueta EXIF 6: o celular mostra em pé."""
    from PIL import Image

    imagem = Image.new("RGB", (400, 300), "white")
    exif = imagem.getexif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    imagem.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


class FotoDoComprovanteEmPeTests(SimpleTestCase):
    """m082: a foto anexada à mão entra no pacote em A4 e em pé, como no importador."""

    def test_foto_com_exif_vira_pagina_a4_em_pe(self):
        from pypdf import PdfReader

        from .services import _image_bytes_to_pdf

        pagina = PdfReader(io.BytesIO(_image_bytes_to_pdf(_foto_deitada_com_exif_em_pe()))).pages[0]
        largura, altura = float(pagina.mediabox.width), float(pagina.mediabox.height)
        self.assertGreater(altura, largura)
        self.assertAlmostEqual(largura, 595.28, delta=2)


class ComprovantePelaListaSomaTests(PrestacaoFixturesMixin, PrestacaoTestCase):
    """m081: anexar pelo menu da lista soma o comprovante aos que já estavam lá."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=81)
        self.ps = self.fixture.prestacoes_servidor[0]

    def _pela_etapa3(self, nome):
        return self.client.post(
            reverse("viagens_prestacoes:prestacao_servidor_arquivo_autosave", args=[self.ps.pk]),
            {f"ps-{self.ps.pk}-comprovante_arquivos": SimpleUploadedFile(nome, pdf_minimo(nome), content_type="application/pdf")},
        )

    def _pela_lista(self, nome, conteudo=None):
        return self.client.post(
            reverse("viagens_prestacoes:prestacao_servidor_assinado_anexar", args=[self.ps.pk, Anexo.TIPO_COMPROVANTE]),
            {"arquivo": SimpleUploadedFile(nome, conteudo or pdf_minimo(nome), content_type="application/pdf")},
        )

    def test_terceiro_comprovante_pela_lista_mantem_os_dois_primeiros(self):
        self._pela_etapa3("c1.pdf")
        self._pela_etapa3("c2.pdf")
        self._pela_lista("c3.pdf")
        nomes = sorted(self.ps.documentos_anexos.filter(tipo=Anexo.TIPO_COMPROVANTE).values_list("nome_original", flat=True))
        self.assertEqual(nomes, ["c1.pdf", "c2.pdf", "c3.pdf"])

    def test_mesmo_arquivo_duas_vezes_nao_duplica(self):
        igual = pdf_minimo("igual")
        self._pela_lista("c1.pdf", igual)
        self._pela_lista("c1-de-novo.pdf", igual)
        self.assertEqual(self.ps.documentos_anexos.filter(tipo=Anexo.TIPO_COMPROVANTE).count(), 1)


class NumeroPreenchidoDepoisDoAnexoTests(PrestacaoFixturesMixin, PrestacaoTestCase):
    """m080: o número digitado depois de anexar o ofício assinado entra no PDF."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=80, servidores=(self.criar_servidor("Joao Da Silva"), self.criar_servidor("Maria Souza")))
        self.prestacao = self.fixture.prestacao
        self.joao, self.maria = self.fixture.prestacoes_servidor
        self.joao.numero_solicitacao = "2026001234"
        self.joao.save(update_fields=["numero_solicitacao"])
        referencia = pdf_do_oficio([("Joao Da Silva", "2026001234"), ("Maria Souza", "2026005678")])
        patch = mock.patch("viagens_prestacoes.services.gerar_oficio_prestacao_pdf", return_value=referencia)
        patch.start()
        self.addCleanup(patch.stop)
        cru = pdf_do_oficio([("Joao Da Silva", ""), ("Maria Souza", "")], com_numero=False)
        self.client.post(
            reverse("viagens_prestacoes:prestacao_oficio_assinado_anexar", args=[self.prestacao.pk]),
            {"arquivo": SimpleUploadedFile("oficio.pdf", cru, content_type="application/pdf")},
        )
        self.anexo = self.prestacao.documentos_anexos.get(tipo=Anexo.TIPO_OFICIO_ASSINADO)

    def _textos(self):
        self.anexo.refresh_from_db()
        with self.anexo.arquivo.open("rb") as arquivo:
            return [f.texto for f in ler_fragmentos(arquivo.read())]

    def test_pelo_autosave(self):
        self.assertNotIn("2026005678", self._textos())
        with self.captureOnCommitCallbacks(execute=True):
            salvar_solicitacao_do_autosave(self.maria, numero="2026005678")
        textos = self._textos()
        self.assertIn("2026001234", textos)
        self.assertIn("2026005678", textos)

    def test_pelo_lote_da_lista(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("viagens_prestacoes:index"), {f"ps-{self.maria.pk}-numero_solicitacao": "2026005678"})
        self.assertIn("2026005678", self._textos())

    def test_oficio_anexado_antes_de_qualquer_numero(self):
        """O caso mais comum: o ofício volta do eProtocolo antes das solicitações."""
        self.anexo.carimbos.all().delete()
        with self.captureOnCommitCallbacks(execute=True):
            salvar_solicitacao_do_autosave(self.maria, numero="2026005678")
        self.assertEqual(self.anexo.carimbos.count(), 2)
        textos = self._textos()
        self.assertIn("2026005678", textos)
        self.assertEqual(textos.count("2026001234"), 1)


class RascunhoDoNavegadorTests(PrestacaoFixturesMixin, PrestacaoTestCase):
    """m083: a Etapa 3 não usa o id do formulário de Solicitação de Evento."""

    def test_etapa3_sem_o_id_do_rascunho(self):
        self.setUpPrestacaoFixtures()
        ps = self.criar_prestacao(numero=83).prestacoes_servidor[0]
        resposta = self.client.get(reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk]))
        self.assertNotContains(resposta, 'id="form-solicitacao"')
        self.assertContains(resposta, 'id="form-prestacao-solicitacao"')


class FinalizarSemInverterTests(PrestacaoFixturesMixin, PrestacaoTestCase):
    """m089: cada botão diz o que quer; clicar de novo não desfaz."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.ps = self.criar_prestacao(numero=89).prestacoes_servidor[0]

    def _post(self, rota, acao):
        return self.client.post(reverse(f"viagens_prestacoes:{rota}", args=[self.ps.pk]), {"acao": acao, "justificativa": "teste"})

    def test_finalizar_duas_vezes_continua_finalizada(self):
        self._post("prestacao_servidor_finalizar", "finalizar")
        self._post("prestacao_servidor_finalizar", "finalizar")
        self.ps.refresh_from_db()
        self.assertTrue(self.ps.finalizada)

    def test_arquivar_duas_vezes_continua_arquivada(self):
        self._post("prestacao_servidor_arquivar", "arquivar")
        self._post("prestacao_servidor_arquivar", "arquivar")
        self.ps.refresh_from_db()
        self.assertTrue(self.ps.arquivada)
        self._post("prestacao_servidor_arquivar", "desarquivar")
        self.ps.refresh_from_db()
        self.assertFalse(self.ps.arquivada)


class LiberacaoDepoisDoPrazoTests(PrestacaoFixturesMixin, PrestacaoTestCase):
    """m090: liberação depois do prazo vira mensagem, não Erro 500."""

    def setUp(self):
        super().setUp()
        import datetime

        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=90, servidores=(self.criar_servidor("Ana"), self.criar_servidor("Bia")))
        self.ana, self.bia = self.fixture.prestacoes_servidor
        for ps in (self.ana, self.bia):
            ps.data_liberacao_diarias = datetime.date(2026, 8, 10)
            ps.prazo_limite_saque = datetime.date(2026, 8, 24)
            ps.save()

    def test_autosave(self):
        from .solicitacao_services import MENSAGEM_PRAZO_ANTES_DA_LIBERACAO

        resultado = salvar_solicitacao_do_autosave(self.ana, datas={"data_liberacao_diarias": "2026-08-30"})
        self.assertEqual(resultado.erro, MENSAGEM_PRAZO_ANTES_DA_LIBERACAO)
        self.ana.refresh_from_db()
        self.assertEqual(str(self.ana.data_liberacao_diarias), "2026-08-10")

    def test_lote_nao_derruba_a_lista(self):
        resposta = self.client.post(reverse("viagens_prestacoes:index"), {
            f"ps-{self.ana.pk}-data_liberacao_diarias": "2026-08-30",
            f"ps-{self.bia.pk}-numero_solicitacao": "123",
        }, follow=True)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "não pode ser anterior à liberação")


class PrazoParaPrestarTests(PrestacaoFixturesMixin, PrestacaoTestCase):
    """m094: 3 dias úteis depois do FIM DO PRAZO DE SAQUE, contando feriados."""

    def setUp(self):
        super().setUp()
        import datetime

        self.D = datetime.date
        self.setUpPrestacaoFixtures()
        self.ps = self.criar_prestacao(numero=94, data_liberacao_diarias=self.D(2026, 8, 20)).prestacoes_servidor[0]
        self.ps.prazo_limite_saque = self.D(2026, 9, 4)
        self.ps.save()

    def test_prazo_pula_o_sete_de_setembro(self):
        from .prazos import prazo_para_prestar

        self.assertEqual(prazo_para_prestar(self.D(2026, 9, 4)), self.D(2026, 9, 10))

    def test_selo_faltam_e_vencida(self):
        from .prazos import selo_da_prestacao

        self.assertIn("faltam 2 dias úteis", selo_da_prestacao(self.ps, hoje=self.D(2026, 9, 8)).texto)
        vencida = selo_da_prestacao(self.ps, hoje=self.D(2026, 9, 11))
        self.assertEqual(vencida.tom, "vencido")

    def test_aba_prestacao_vencida(self):
        from .selectors import listar_prestacoes

        with mock.patch("django.utils.timezone.localdate", return_value=self.D(2026, 9, 11)):
            self.assertIn(self.ps.pk, set(listar_prestacoes(aba="prestacao_vencida").values_list("pk", flat=True)))
        with mock.patch("django.utils.timezone.localdate", return_value=self.D(2026, 9, 10)):
            self.assertNotIn(self.ps.pk, set(listar_prestacoes(aba="prestacao_vencida").values_list("pk", flat=True)))


class VersoesAnterioresTests(PrestacaoFixturesMixin, PrestacaoTestCase):
    """m084: remover e substituir guardam o anterior, que se restaura."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=84)
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]

    def _rt(self, nome):
        self.client.post(
            reverse("viagens_prestacoes:prestacao_servidor_assinado_anexar", args=[self.ps.pk, Anexo.TIPO_RT_ASSINADO]),
            {"arquivo": SimpleUploadedFile(nome, pdf_minimo(nome), content_type="application/pdf")},
        )
        return Anexo.todos.get(nome_original=nome)

    def _restaurar(self, anexo):
        return self.client.post(reverse("viagens_prestacoes:prestacao_documento_restaurar", args=[self.prestacao.pk, anexo.pk]))

    def test_substituir_guarda_o_anterior_e_voltar_troca_de_lugar(self):
        antigo = self._rt("rt-1.pdf")
        novo = self._rt("rt-2.pdf")
        antigo.refresh_from_db()
        self.assertEqual(antigo.removido_motivo, Anexo.REMOVIDO_SUBSTITUIDO)
        self._restaurar(antigo)
        ativos = list(self.ps.documentos_anexos.filter(tipo=Anexo.TIPO_RT_ASSINADO).values_list("nome_original", flat=True))
        self.assertEqual(ativos, ["rt-1.pdf"])
        novo.refresh_from_db()
        self.assertIsNotNone(novo.removido_em)

    def test_remover_e_desfazer(self):
        anexo = self._rt("rt-1.pdf")
        self.client.post(reverse("viagens_prestacoes:prestacao_documento_delete", args=[self.prestacao.pk, anexo.pk]))
        self.assertFalse(self.ps.documentos_anexos.exists())
        pagina = self.client.get(reverse("viagens_prestacoes:documentos_servidor", args=[self.ps.pk]))
        self.assertContains(pagina, "Versões anteriores (1)")
        self._restaurar(anexo)
        self.assertTrue(self.ps.documentos_anexos.filter(pk=anexo.pk).exists())

    def test_versao_anterior_do_oficio_volta_com_os_carimbos(self):
        from .models import CarimboSolicitacao

        anexo = Anexo.objects.create(prestacao=self.prestacao, tipo=Anexo.TIPO_OFICIO_ASSINADO, arquivo=SimpleUploadedFile("o.pdf", pdf_minimo()), nome_original="o.pdf")
        CarimboSolicitacao.objects.create(anexo=anexo, servidor_prestacao=self.ps, x=0.5, y=0.5, ajustado_manualmente=True)
        self.client.post(reverse("viagens_prestacoes:prestacao_documento_delete", args=[self.prestacao.pk, anexo.pk]))
        self._restaurar(anexo)
        self.assertTrue(anexo.carimbos.filter(ajustado_manualmente=True).exists())
