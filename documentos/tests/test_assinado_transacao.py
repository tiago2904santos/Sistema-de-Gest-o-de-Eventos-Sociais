"""Anexar o assinado é tudo ou nada, como a geração.

`anexar_arquivo_assinado` grava o arquivo da versão antes da linha no banco. Se
a gravação falha — nela mesma ou depois, na operação maior que a chamou (o
importador de processo anexa vários documentos numa transação só) —, o arquivo
tem de sair junto com o rollback, e não ficar órfão em
`documentos/assinados/versoes/`.
"""

import tempfile
from pathlib import Path
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings

from documentos.models import DocumentoArtefato
from documentos.models import DocumentoAssinaturaVersao
from documentos.services.persistence import anexar_arquivo_assinado
from viagens_prestacoes.arquivos import transacao_de_arquivos


class AnexarAssinadoTudoOuNadaTests(TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory(prefix="assinado_transacao_")
        self.addCleanup(pasta.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=pasta.name))
        self.media = Path(pasta.name)
        self.artefato = DocumentoArtefato(tipo="oficio", formato="pdf", hash_sha256="0" * 64, nome_exibicao="oficio_1-2026_x.pdf")
        self.artefato.arquivo.save("gerado.pdf", ContentFile(b"%PDF-1.4 gerado"), save=False)
        self.artefato.save()

    def versoes_no_disco(self):
        return [p for p in self.media.rglob("*") if p.is_file() and "versoes" in p.parts]

    def upload(self):
        return SimpleUploadedFile("assinado.pdf", b"%PDF-1.4 assinado", content_type="application/pdf")

    def test_anexa_normalmente(self):
        anexar_arquivo_assinado(self.artefato, self.upload())
        self.assertEqual(self.artefato.versoes_assinadas.count(), 1)
        self.assertEqual(len(self.versoes_no_disco()), 1)

    def test_falha_ao_gravar_a_versao_apaga_o_arquivo(self):
        with mock.patch.object(DocumentoAssinaturaVersao, "save", side_effect=RuntimeError("banco fora")):
            with self.assertRaises(RuntimeError):
                anexar_arquivo_assinado(self.artefato, self.upload())
        self.assertEqual(self.versoes_no_disco(), [])

    def test_falha_ao_gravar_o_artefato_desfaz_a_versao_e_apaga_o_arquivo(self):
        with mock.patch.object(DocumentoArtefato, "save", side_effect=RuntimeError("banco fora")):
            with self.assertRaises(RuntimeError):
                anexar_arquivo_assinado(self.artefato, self.upload())
        self.assertFalse(DocumentoAssinaturaVersao.objects.exists())
        self.assertEqual(self.versoes_no_disco(), [])

    def test_rollback_da_operacao_maior_leva_a_versao_e_o_arquivo(self):
        with self.assertRaises(RuntimeError):
            with transacao_de_arquivos():
                anexar_arquivo_assinado(self.artefato, self.upload())
                self.assertEqual(len(self.versoes_no_disco()), 1)
                raise RuntimeError("falhou o documento seguinte")
        self.assertFalse(DocumentoAssinaturaVersao.objects.exists())
        self.assertEqual(self.versoes_no_disco(), [])
        self.artefato.refresh_from_db()
        self.assertFalse(self.artefato.arquivo_assinado)
        self.assertTrue((self.media / self.artefato.arquivo.name).exists())  # o PDF gerado continua
