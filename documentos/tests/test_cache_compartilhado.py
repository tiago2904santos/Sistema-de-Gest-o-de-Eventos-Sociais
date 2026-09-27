"""Cache de artefatos entre usuários e estável entre deploys (m127)."""

import os
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from documentos.models import DocumentoArtefato
from documentos.services.document_cache import _file_fp
from documentos.services.types import DocumentoFormato
from viagens_oficios.tests.fixtures import CenarioOficioMixin


class ImpressaoDoArquivoTests(SimpleTestCase):
    def test_conteudo_igual_com_outra_data_e_a_mesma_impressao(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "modelo.css"
            arquivo.write_text("body { color: red }", encoding="utf-8")
            antes = _file_fp(arquivo)
            # Um deploy reescreve o arquivo igual: outro mtime, mesmo conteúdo.
            os.utime(arquivo, (1_600_000_000, 1_600_000_000))
            self.assertEqual(_file_fp(arquivo), antes)
            arquivo.write_text("body { color: blue }", encoding="utf-8")
            self.assertNotEqual(_file_fp(arquivo), antes)
            self.assertNotIn(pasta, _file_fp(arquivo))
            self.assertTrue(_file_fp(Path(pasta) / "nada.css").endswith(":missing"))


class CacheEntreUsuariosTests(CenarioOficioMixin, TestCase):
    def test_o_pdf_gerado_por_um_colega_e_reaproveitado(self):
        oficio = self.criar()
        with self.settings(DOCUMENTOS_ARTIFACT_CACHE=True):
            from documentos.services.facade import DocumentoFacade
            from documentos.services.types import DocumentoTipo
            from viagens_oficios.documents import build_canonical_document_payload
            from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context

            colega = get_user_model().objects.create_user(username="colega", deve_trocar_senha=False)
            payload = build_canonical_document_payload(oficio, DocumentoTipo.OFICIO)
            contexto = build_oficio_docxtpl_context(oficio)

            def gerar(usuario):
                return DocumentoFacade().gerar(
                    tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.DOCX, payload=payload, reference="1-2026",
                    docxtpl_context=contexto, oficio_id=oficio.pk, criado_por=usuario,
                )

            meu = gerar(self.user)
            self.assertFalse(meu.cache_hit)
            do_colega = gerar(colega)
            self.assertTrue(do_colega.cache_hit)
            self.assertEqual(do_colega.artefato_id, meu.artefato_id)
            self.assertEqual(DocumentoArtefato.objects.filter(oficio=oficio, formato="docx").count(), 1)
            self.assertEqual(DocumentoArtefato.objects.get(pk=meu.artefato_id).criado_por, self.user)
