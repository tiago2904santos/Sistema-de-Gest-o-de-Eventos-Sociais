"""Contratos da F3 no sistema unificado: banco, cache, auditoria e acesso."""

import hashlib
import io
import tempfile
import uuid
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse

from accounts.models import Modulo, Setor
from auditoria.models import RegistroAuditoria
from core.middleware import RequisicaoAtualMiddleware
from documentos.models import DocumentoArtefato
from documentos.services.facade import DocumentoFacade
from documentos.services.formatters import format_currency_br, format_document_datetime
from documentos.services.persistence import anexar_arquivo_assinado, remover_arquivo_assinado
from documentos.services.types import DocumentoFormato, DocumentoTipo
from viagens_cadastros.models import Servidor
from viagens_roteiros.models import Roteiro


def payload_exemplo():
    return {
        "institucional": {"nome_orgao": "PCPR", "unidade": "Teste F3"},
        "oficio": {"numero_formatado": "F3/2026", "assunto": "Teste F3", "roteiro": "Curitiba"},
        "justificativa": {"exigida": True, "texto": "Teste F3"},
        "termo": {"participante": {"nome": "Teste F3"}},
    }


# A cadeia antiga (DOCX → conversor) continua valendo para os tipos ainda não
# migrados; aqui ela é exercitada com o ofício, então o caminho HTML nativo é
# desligado só neste teste.
@override_settings(DOCUMENTOS_PDF_HTML_NATIVO=())
class ArtefatosTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="eventos_f3_test_")
        self.addCleanup(folder.cleanup)
        self.media = Path(folder.name)
        override = override_settings(MEDIA_ROOT=folder.name, DOCUMENTOS_DEFAULT_PDF_ENGINE="simple")
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_user(username="documentos", deve_trocar_senha=False)
        self.facade = DocumentoFacade()

    def gerar(self, **kwargs):
        params = dict(tipo=DocumentoTipo.OFICIO, formato=DocumentoFormato.DOCX,
                      payload=payload_exemplo(), reference="teste-f3", criado_por=self.user)
        params.update(kwargs)
        return self.facade.gerar(**params)

    def permitir_viagens(self):
        modulo = Modulo.objects.get(codigo="VIAGENS")
        setor = Setor.objects.create(nome="Teste documentos")
        modulo.setores.add(setor)
        self.user.setores.add(setor)

    def baixar(self, artefato_id):
        response = self.client.get(reverse("documentos:baixar", args=[artefato_id]))
        if response.streaming:
            response.downloaded_content = b"".join(response.streaming_content)
        return response

    def test_persiste_hash_snapshot_arquivo_e_fks(self):
        servidor = Servidor.objects.create(nome="Pessoa F3")
        roteiro = Roteiro.objects.create()
        payload = payload_exemplo()
        payload["valor"] = Decimal("43.58")
        with self.captureOnCommitCallbacks(execute=True):
            doc = self.gerar(payload=payload, servidor_id=servidor.pk, roteiro_id=roteiro.pk)
        art = DocumentoArtefato.objects.get(pk=doc.artefato_id)
        self.assertEqual(art.hash_sha256, hashlib.sha256(doc.conteudo).hexdigest())
        self.assertEqual(art.payload_snapshot["valor"], "43.58")
        self.assertEqual(art.servidor, servidor)
        self.assertEqual(art.roteiro, roteiro)
        self.assertEqual(art.criado_por, self.user)
        self.assertEqual(art.nome_exibicao, doc.nome_arquivo)
        self.assertEqual(art.engine, "docxtpl")
        with art.arquivo.open("rb") as f:
            self.assertEqual(f.read(), doc.conteudo)
        self.assertTrue(RegistroAuditoria.objects.filter(objeto_id=str(art.pk)).exists())

    def test_trilha_registra_o_artefato_sem_copiar_o_payload(self):
        """A trilha guarda quem gerou e o quê, não o conteúdo do documento.

        O payload carrega dado pessoal (nome, CPF, lotação) e já vive no
        artefato; repetido na auditoria, multiplicaria o dado sem acrescentar
        rastro nenhum.
        """
        payload = payload_exemplo()
        payload["cpf_do_servidor"] = "12345678901"
        with self.captureOnCommitCallbacks(execute=True):
            doc = self.gerar(payload=payload)
        registro = RegistroAuditoria.objects.get(objeto_id=str(doc.artefato_id))
        self.assertNotIn("payload_snapshot", registro.alteracoes["novo"])
        self.assertNotIn("12345678901", str(registro.alteracoes))
        # O rastro continua existindo e apontando para o artefato certo.
        self.assertEqual(registro.modelo, "documentos.documentoartefato")

    def test_repeticao_reutiliza_artefato_sem_render_nem_arquivo_novo(self):
        first = self.gerar()
        with mock.patch.object(self.facade, "_render_docx", side_effect=AssertionError("cache perdido")):
            second = self.gerar()
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.artefato_id, second.artefato_id)
        self.assertEqual(first.conteudo, second.conteudo)
        self.assertEqual(DocumentoArtefato.objects.count(), 1)
        self.assertEqual(len([p for p in self.media.rglob("*") if p.is_file()]), 1)

    def test_payload_alterado_invalida_cache(self):
        first = self.gerar()
        payload = payload_exemplo()
        payload["oficio"]["numero_formatado"] = "OUTRO"
        self.assertNotEqual(first.artefato_id, self.gerar(payload=payload).artefato_id)

    def test_contexto_docxtpl_alterado_invalida_cache(self):
        first = self.gerar(docxtpl_context={"oficio": "1"})
        second = self.gerar(docxtpl_context={"oficio": "2"})
        self.assertNotEqual(first.artefato_id, second.artefato_id)

    def test_versao_do_gerador_invalida_cache(self):
        first = self.gerar()
        with override_settings(DOCUMENTOS_GENERATOR_VERSION="v2"):
            second = self.gerar()
        self.assertNotEqual(first.artefato_id, second.artefato_id)

    def test_cache_respeita_vinculos_opcionais_e_criador(self):
        first = self.gerar()
        servidor = Servidor.objects.create(nome="Pessoa F3")
        linked = self.gerar(servidor_id=servidor.pk)
        outro = get_user_model().objects.create_user(username="outro")
        other_actor = self.gerar(criado_por=outro)
        self.assertEqual(len({first.artefato_id, linked.artefato_id, other_actor.artefato_id}), 3)

    def test_arquivo_ausente_regenera(self):
        first = self.gerar()
        art = DocumentoArtefato.objects.get(pk=first.artefato_id)
        art.arquivo.storage.delete(art.arquivo.name)
        self.assertNotEqual(first.artefato_id, self.gerar().artefato_id)

    def test_pdf_persiste_motor_e_cache(self):
        first = self.gerar(formato=DocumentoFormato.PDF)
        second = self.gerar(formato=DocumentoFormato.PDF)
        self.assertEqual(first.pdf_engine_used, "simple_fallback")
        self.assertEqual(first.artefato_id, second.artefato_id)
        self.assertTrue(second.cache_hit)

    def test_download_anonimo_redireciona_login(self):
        response = self.baixar(self.gerar().artefato_id)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_download_sem_modulo_negado_mesmo_ao_criador(self):
        self.client.force_login(self.user)
        self.assertEqual(self.baixar(self.gerar().artefato_id).status_code, 403)

    def test_download_com_modulo_permitido_e_privado(self):
        self.permitir_viagens()
        self.client.force_login(self.user)
        doc = self.gerar()
        response = self.baixar(doc.artefato_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.downloaded_content, doc.conteudo)
        self.assertEqual(response["Content-Type"], doc.content_type)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store, must-revalidate")
        self.assertNotIn("X-Accel-Redirect", response)
        art = DocumentoArtefato.objects.get(pk=doc.artefato_id)
        self.assertEqual(self.client.get("/media/" + art.arquivo.name).status_code, 404)

    def test_download_superusuario_sem_setor(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(self.baixar(self.gerar().artefato_id).status_code, 200)

    def test_download_modulo_inativo_negado(self):
        self.permitir_viagens()
        Modulo.objects.filter(codigo="VIAGENS").update(ativo=False)
        self.client.force_login(self.user)
        self.assertEqual(self.baixar(self.gerar().artefato_id).status_code, 403)

    def test_artefato_inexistente_404_para_usuario_autorizado(self):
        self.permitir_viagens()
        self.client.force_login(self.user)
        self.assertEqual(self.baixar(uuid.uuid4()).status_code, 404)

    def test_arquivo_inexistente_404(self):
        self.permitir_viagens()
        self.client.force_login(self.user)
        doc = self.gerar()
        art = DocumentoArtefato.objects.get(pk=doc.artefato_id)
        art.arquivo.storage.delete(art.arquivo.name)
        self.assertEqual(self.baixar(doc.artefato_id).status_code, 404)

    def test_assinado_preferido_com_content_type_e_extensao_pdf(self):
        self.permitir_viagens()
        self.client.force_login(self.user)
        art = DocumentoArtefato.objects.get(pk=self.gerar().artefato_id)
        raw = b"%PDF-1.7 assinado"
        anexar_arquivo_assinado(art, SimpleUploadedFile("assinado.pdf", raw))
        response = self.baixar(art.pk)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(".pdf", response["Content-Disposition"])
        self.assertEqual(response.downloaded_content, raw)
        versao = art.versoes_assinadas.get()
        self.assertEqual(versao.hash_sha256, hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValidationError):
            versao.delete()
        versao.nome_original = "alterado.pdf"
        with self.assertRaises(ValidationError):
            versao.save()
        remover_arquivo_assinado(art)
        versao.refresh_from_db()
        self.assertIsNotNone(versao.revogada_em)
        self.assertTrue(versao.arquivo.storage.exists(versao.arquivo.name))
        self.assertEqual(art.arquivo_efetivo.name, art.arquivo.name)

    def test_data_do_banco_utc_sai_no_docx_em_sao_paulo(self):
        from docx import Document

        roteiro = Roteiro.objects.create(saida_dt=datetime(2026, 9, 9, 11, tzinfo=dt_timezone.utc))
        roteiro.refresh_from_db()
        doc = self.gerar(docxtpl_context={"col_ida_saida": roteiro.saida_dt})
        document = Document(io.BytesIO(doc.conteudo))
        text = " ".join(c.text for t in document.tables for r in t.rows for c in r.cells)
        self.assertIn("09/09/2026 08:00", text)
        self.assertNotIn("11:00", text)


class FormatacaoLocalTests(SimpleTestCase):
    def test_virada_de_dia_localiza_antes_de_formatar(self):
        utc = datetime(2026, 9, 9, 1, tzinfo=dt_timezone.utc)
        self.assertEqual(format_document_datetime(utc), "08/09/2026 22:00")

    def test_dinheiro_usa_localizacao_django(self):
        with mock.patch("documentos.services.formatters.formats.number_format", return_value="43,58") as fmt:
            self.assertEqual(format_currency_br(Decimal("43.58")), "R$43,58")
        fmt.assert_called_once_with(Decimal("43.58"), decimal_pos=2, force_grouping=True)
