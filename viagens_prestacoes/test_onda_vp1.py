"""Onda V-P1 da prestação de contas (m080–m094): regressões de cada item."""

from __future__ import annotations

import datetime
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


class SelosDoDiarioEDoRelatorioTests(PrestacaoFixturesMixin, PrestacaoTestCase):
    """m091: abrir a tela não acende selo; preenchido = "gerado"; ✓ só com o assinado."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=91)
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]

    def test_tres_estados(self):
        from .completude import GERADO, ASSINADO, situacao_diario, situacao_rt
        from .models import DiarioBordo, DiarioBordoTrecho, RelatorioTecnico

        diario = DiarioBordo.objects.create(prestacao=self.prestacao)
        trecho = DiarioBordoTrecho.objects.create(diario=diario, ordem=0)
        rt = RelatorioTecnico.objects.create(prestacao=self.prestacao)
        self.assertEqual((situacao_diario(self.prestacao), situacao_rt(self.ps)), ("", ""))

        trecho.km_inicial, trecho.km_final = 100, 180
        trecho.save()
        rt.motivo, rt.atividade, rt.conclusao = "Evento", "Cobertura", "Concluído"
        rt.save()
        self.prestacao.refresh_from_db()
        self.assertEqual((situacao_diario(self.prestacao), situacao_rt(self.ps)), (GERADO, GERADO))

        Anexo.objects.create(prestacao=self.prestacao, servidor_prestacao=self.ps, tipo=Anexo.TIPO_RT_ASSINADO, arquivo=SimpleUploadedFile("rt.pdf", pdf_minimo()))
        self.assertEqual(situacao_rt(self.ps), ASSINADO)

    def test_lista_nao_acende_so_por_abrir_a_tela(self):
        self.client.get(reverse("viagens_prestacoes:diario_servidor", args=[self.ps.pk]))
        self.client.get(reverse("viagens_prestacoes:rt_servidor", args=[self.ps.pk]))
        resposta = self.client.get(reverse("viagens_prestacoes:index"))
        self.assertNotContains(resposta, "Diário gerado")
        self.assertNotContains(resposta, 'title="Relatório técnico assinado anexado"')


class AvisosNoSinoTests(PrestacaoFixturesMixin, PrestacaoTestCase):
    """m085/m090: selo e aba do saque; avisos no sino (liberadas, vencendo, vencidas, documentos)."""

    def setUp(self):
        super().setUp()
        import datetime

        from django.contrib.auth import get_user_model

        from .test_helpers import autorizar_viagens

        self.D = datetime.date
        self.setUpPrestacaoFixtures()
        self.colega = get_user_model().objects.create_user(username="colega_viagens", password="x")
        autorizar_viagens(self.colega)
        self.ps = self.criar_prestacao(numero=85).prestacoes_servidor[0]

    def _titulos(self, usuario):
        return list(usuario.notificacoes.values_list("titulo", flat=True))

    def test_diarias_liberadas_avisa_os_colegas_e_nao_o_autor(self):
        from .solicitacao_services import salvar_solicitacao_do_autosave

        with self.captureOnCommitCallbacks(execute=True):
            salvar_solicitacao_do_autosave(self.ps, datas={"data_liberacao_diarias": "2026-08-10", "prazo_limite_saque": "2026-08-24"}, autor=self.user)
        self.assertTrue(any(t.startswith("Diárias liberadas") for t in self._titulos(self.colega)))
        self.assertFalse(self._titulos(self.user))

    def test_saque_vencendo_vencido_e_prestacao_vencida_uma_vez_so(self):
        from .avisos import avisar_prazos

        self.ps.data_liberacao_diarias = self.D(2026, 8, 20)
        self.ps.prazo_limite_saque = self.D(2026, 9, 4)
        self.ps.save()
        avisar_prazos(hoje=self.D(2026, 9, 2))
        self.assertTrue(any(t.startswith("Saque vence em 2 dias") for t in self._titulos(self.colega)))
        avisar_prazos(hoje=self.D(2026, 9, 2))
        self.assertEqual(len(self._titulos(self.colega)), 1)
        avisar_prazos(hoje=self.D(2026, 9, 11))
        titulos = self._titulos(self.colega)
        self.assertTrue(any(t.startswith("Prazo de saque vencido") for t in titulos))
        self.assertTrue(any(t.startswith("Prestação vencida") for t in titulos))

    def test_selo_e_aba_do_saque(self):
        from .prazos import selo_do_saque
        from .selectors import listar_prestacoes

        self.ps.prazo_limite_saque = timezone_hoje() + datetime.timedelta(days=2)
        self.ps.data_liberacao_diarias = timezone_hoje()
        self.ps.save()
        self.assertEqual(selo_do_saque(self.ps, tem_comprovante=False).texto, "Saque vence em 2 dias")
        self.assertIsNone(selo_do_saque(self.ps, tem_comprovante=True))
        self.assertIn(self.ps.pk, set(listar_prestacoes(aba="saque_vencendo").values_list("pk", flat=True)))
        Anexo.objects.create(prestacao=self.ps.prestacao, servidor_prestacao=self.ps, tipo=Anexo.TIPO_COMPROVANTE, arquivo=SimpleUploadedFile("c.pdf", pdf_minimo()))
        self.assertNotIn(self.ps.pk, set(listar_prestacoes(aba="saque_vencendo").values_list("pk", flat=True)))

    def test_comando_diario(self):
        from io import StringIO

        from django.core.management import call_command

        saida = StringIO()
        call_command("avisar_prazos_prestacao", stdout=saida)
        self.assertIn("aviso(s)", saida.getvalue())


def timezone_hoje():
    from django.utils import timezone

    return timezone.localdate()


class PendenciasETravaTests(PrestacaoFixturesMixin, PrestacaoTestCase):
    """m092: finalizar confere pendências; finalizada fica só para leitura."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=92, servidores=(self.criar_servidor("Ana"), self.criar_servidor("Bia")))
        self.prestacao = self.fixture.prestacao
        self.ana, self.bia = self.fixture.prestacoes_servidor

    def test_lista_de_pendencias_inclui_diario_rt_e_soma(self):
        from decimal import Decimal

        from .services import pendencias_para_finalizar

        self.ana.diaria_valor_override = Decimal("300.00")
        self.ana.save()
        Anexo.objects.create(prestacao=self.prestacao, servidor_prestacao=self.ana, tipo=Anexo.TIPO_COMPROVANTE, arquivo=SimpleUploadedFile("c.pdf", pdf_minimo()), valor=Decimal("250.00"))
        texto = " ".join(pendencias_para_finalizar(self.ana))
        self.assertIn("diário de bordo", texto)
        self.assertIn("relatório técnico", texto)
        self.assertIn("somam R$", texto)

    def test_finalizada_trava_o_autosave_do_servidor(self):
        self.ana.definir_finalizada(True)
        resposta = self.client.post(
            reverse("viagens_prestacoes:prestacao_servidor_solicitacao_autosave", args=[self.ana.pk]),
            data='{"model": "prestacao_servidor", "fields": {"numero_solicitacao": "999"}}',
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 409)
        self.assertIn("reabra para editar", resposta.json()["message"])
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.numero_solicitacao, "")

    def test_compartilhado_so_trava_com_a_equipe_toda_finalizada(self):
        from .trava import _travada

        self.ana.definir_finalizada(True)
        self.assertFalse(_travada("prestacao_despacho_assinado_anexar", {"pc_pk": self.prestacao.pk}))
        self.bia.definir_finalizada(True)
        self.assertTrue(_travada("prestacao_despacho_assinado_anexar", {"pc_pk": self.prestacao.pk}))

    def test_equipe_nao_finaliza_quem_tem_pendencia(self):
        self.client.post(reverse("viagens_prestacoes:prestacao_equipe_acao", args=[self.prestacao.pk, "finalizar"]))
        self.ana.refresh_from_db()
        self.assertFalse(self.ana.finalizada)


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
