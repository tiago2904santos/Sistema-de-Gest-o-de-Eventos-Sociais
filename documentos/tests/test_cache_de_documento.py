"""O navegador servia o PDF antigo depois de retificar o ofício.

"Visualizar" e o iframe de pré-visualização apontam sempre para a mesma URL por
documento. O servidor já regenerava o arquivo a cada chamada — o cache interno é
por hash do conteúdo, então muda sozinho quando o documento muda. O que faltava
era dizer isso ao navegador: sem `Cache-Control`, ele pode reaproveitar a
resposta anterior daquela URL e mostrar a versão pré-retificação.

Documento oficial que vai para assinatura não pode ser servido de cache do
navegador. Rascunho #44, aberto em 14/07/2026; confirmei que os cabeçalhos
continuavam ausentes.

O `X-Document-Cache` é outra coisa e continua igual: ele reporta se o **servidor**
reaproveitou o binário, e é usado pelos testes de SLA.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.test import SimpleTestCase

from documentos.services.pdf_streaming import apply_pdf_response_headers
from documentos.services.responses import build_download_response
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo


class CabecalhosDeCacheTests(SimpleTestCase):
    def test_pdf_inline_manda_o_navegador_nao_guardar(self):
        response = HttpResponse(b"%PDF-1.7")

        apply_pdf_response_headers(response, filename="oficio.pdf")

        self.assertEqual(response["Cache-Control"], "no-store, must-revalidate")
        self.assertEqual(response["Pragma"], "no-cache")

    def test_pdf_inline_preserva_os_demais_cabecalhos(self):
        """A correção não pode custar o `Accept-Ranges`: o viewer usa Range."""
        response = HttpResponse(b"%PDF-1.7")

        apply_pdf_response_headers(response, filename="oficio.pdf")

        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["Accept-Ranges"], "bytes")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("inline", response["Content-Disposition"])

    def test_download_manda_o_navegador_nao_guardar(self):
        response = build_download_response(
            content=b"%PDF-1.7",
            tipo=DocumentoTipo.OFICIO,
            formato=DocumentoFormato.PDF,
            reference="oficio-1",
        )

        self.assertEqual(response["Cache-Control"], "no-store, must-revalidate")
        self.assertEqual(response["Pragma"], "no-cache")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_o_x_document_cache_continua_reportando_o_cache_do_servidor(self):
        """São dois caches diferentes; o do servidor segue sendo informado."""
        for cache_hit, esperado in ((True, "HIT"), (False, "MISS")):
            with self.subTest(cache_hit=cache_hit):
                response = build_download_response(
                    content=b"%PDF-1.7",
                    tipo=DocumentoTipo.OFICIO,
                    formato=DocumentoFormato.PDF,
                    reference="oficio-1",
                    cache_hit=cache_hit,
                )

                self.assertEqual(response["X-Document-Cache"], esperado)
                self.assertEqual(response["Cache-Control"], "no-store, must-revalidate")
