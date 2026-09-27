"""Limpeza semanal de arquivos (core/limpeza.py, m128)."""

import os
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core import limpeza
from core.models import Notificacao
from documentos.models import DocumentoArtefato, DocumentoAssinaturaVersao

User = get_user_model()


def _pdf(numero=1):
    return b"%PDF-1.4\n" + str(numero).encode() + b"\n%%EOF\n"


class LimpezaBase(TestCase):
    def setUp(self):
        cache.clear()
        self._media = TemporaryDirectory()
        self.addCleanup(self._media.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=self._media.name))

    def artefato(self, nome, *, dias=120, versao=None, assinado=False, **campos):
        artefato = DocumentoArtefato.objects.create(
            tipo="oficio", formato="pdf", nome_exibicao=nome, hash_sha256="x" * 64,
            arquivo=ContentFile(_pdf(), name=nome), versao_emitida=versao, **campos,
        )
        if assinado:
            artefato.arquivo_assinado.save("assinado.pdf", ContentFile(_pdf(2)), save=True)
        DocumentoArtefato.objects.filter(pk=artefato.pk).update(criado_em=timezone.now() - timedelta(days=dias))
        artefato.refresh_from_db()
        return artefato

    def envelhecer(self, nome, horas=48):
        caminho = Path(self._media.name) / nome
        antigo = (timezone.now() - timedelta(hours=horas)).timestamp()
        os.utime(caminho, (antigo, antigo))


class ArtefatosTests(LimpezaBase):
    def test_sai_so_o_antigo_sem_protecao_e_que_nao_e_o_mais_recente(self):
        antigo = self.artefato("oficio_1-2026_20260101-090000.pdf", dias=120)
        via = self.artefato("oficio_1-2026_20260102-090000.pdf", dias=110, versao=1)
        assinado = self.artefato("oficio_1-2026_20260103-090000.pdf", dias=100, assinado=True)
        com_versao = self.artefato("oficio_1-2026_20260104-090000.pdf", dias=100)
        DocumentoAssinaturaVersao.objects.create(artefato=com_versao, arquivo=ContentFile(_pdf(3), name="v.pdf"), hash_sha256="y" * 64)
        recente_mas_velho = self.artefato("oficio_1-2026_20260105-090000.pdf", dias=95)
        novo = self.artefato("oficio_1-2026_20260106-090000.pdf", dias=10)
        outro_doc = self.artefato("oficio_2-2026_20260101-090000.pdf", dias=120)
        arquivo_antigo = antigo.arquivo.name

        vencidos = limpeza.expurgar_artefatos(dias=90, apagar=False)
        self.assertEqual({a.pk for a in vencidos}, {antigo.pk, recente_mas_velho.pk})
        self.assertTrue(DocumentoArtefato.objects.filter(pk=antigo.pk).exists())

        limpeza.expurgar_artefatos(dias=90, apagar=True)
        vivos = set(DocumentoArtefato.objects.values_list("pk", flat=True))
        self.assertEqual(vivos, {via.pk, assinado.pk, com_versao.pk, novo.pk, outro_doc.pk})
        self.assertFalse(default_storage.exists(arquivo_antigo))
        self.assertTrue(default_storage.exists(via.arquivo.name))


class OrfaosEImportacoesTests(LimpezaBase):
    def test_orfao_antigo_sai_e_o_recente_fica(self):
        vivo = self.artefato("oficio_1-2026_20260101-090000.pdf", dias=1)
        antigo = default_storage.save("documentos/gerados/2026/01/orfao.pdf", ContentFile(b"orfao"))
        self.envelhecer(antigo)
        recente = default_storage.save("documentos/gerados/2026/01/enviando.pdf", ContentFile(b"em andamento"))
        coffee = default_storage.save("coffee_break/notas/2026/nota-orfa.pdf", ContentFile(b"orfao"))
        self.envelhecer(coffee)
        self.assertCountEqual(limpeza.limpar_orfaos(apagar=False), [coffee, antigo])
        limpeza.limpar_orfaos(apagar=True)
        self.assertFalse(default_storage.exists(antigo))
        self.assertFalse(default_storage.exists(coffee))
        self.assertTrue(default_storage.exists(recente))
        self.assertTrue(default_storage.exists(vivo.arquivo.name))

    def test_planilhas_temporarias_do_coffee_break(self):
        with TemporaryDirectory() as pasta, mock.patch("core.limpeza.pasta_importacao_coffee", return_value=Path(pasta)):
            velha = Path(pasta) / "velha.xlsx"
            velha.write_bytes(b"x")
            antigo = (timezone.now() - timedelta(days=2)).timestamp()
            os.utime(velha, (antigo, antigo))
            nova = Path(pasta) / "nova.xlsx"
            nova.write_bytes(b"x")
            self.assertEqual(limpeza.limpar_importacoes_coffee(apagar=True), ["velha.xlsx"])
            self.assertFalse(velha.exists())
            self.assertTrue(nova.exists())


class RotinaEComandoTests(LimpezaBase):
    def test_rotina_roda_uma_vez_por_semana_e_avisa_a_administracao(self):
        admin = User.objects.create_user("admin", password="x", is_staff=True)
        User.objects.create_user("comum", password="x")
        self.artefato("oficio_1-2026_20260101-090000.pdf", dias=120)
        self.artefato("oficio_1-2026_20260102-090000.pdf", dias=100)
        hoje = date(2026, 9, 28)
        resultado = limpeza.rotina_semanal(hoje)
        self.assertIn("1 PDF/DOCX antigo(s)", resultado)
        self.assertEqual(DocumentoArtefato.objects.count(), 1)
        self.assertEqual(Notificacao.objects.filter(titulo="Limpeza semanal de arquivos").count(), 1)
        self.assertEqual(Notificacao.objects.get(titulo="Limpeza semanal de arquivos").usuario, admin)
        self.assertTrue(limpeza.rotina_semanal(hoje + timedelta(days=3)).startswith("já rodou"))
        with mock.patch("core.limpeza.limpar", return_value={"artefatos": [], "anexos_removidos": [], "orfaos": [], "importacoes_coffee": [], "sessoes": True}) as limpar:
            limpeza.rotina_semanal(hoje + timedelta(days=7))
        self.assertEqual(limpar.call_count, 1)
        # Sem nada removido, sem aviso.
        self.assertEqual(Notificacao.objects.filter(titulo="Limpeza semanal de arquivos").count(), 1)

    def test_comando_simula_sem_apagar_e_apaga_com_a_opcao(self):
        antigo = self.artefato("oficio_1-2026_20260101-090000.pdf", dias=120)
        self.artefato("oficio_1-2026_20260102-090000.pdf", dias=100)
        saida = StringIO()
        call_command("limpar_arquivos", stdout=saida)
        self.assertIn("Documento antigo: oficio_1-2026_20260101-090000.pdf", saida.getvalue())
        self.assertIn("nada foi apagado", saida.getvalue())
        self.assertTrue(DocumentoArtefato.objects.filter(pk=antigo.pk).exists())
        saida = StringIO()
        call_command("limpar_arquivos", "--apagar", "--dias", "90", stdout=saida)
        self.assertIn("Removidos: 1 PDF/DOCX antigo(s)", saida.getvalue())
        self.assertFalse(DocumentoArtefato.objects.filter(pk=antigo.pk).exists())
