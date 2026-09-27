"""Indicador de páginas do editor (m124): quantas páginas o PDF terá e se a
letra foi reduzida, medidos pelo mesmo motor do PDF."""
from unittest import mock, skipUnless

from django.test import TestCase
from django.urls import reverse

from documentos.services.pdf_renderer import weasyprint_disponivel
from viagens_oficios.tests.fixtures import CenarioOficioMixin


class IndicadorDePaginasTests(CenarioOficioMixin, TestCase):
    def test_editor_traz_o_indicador_com_a_rota(self):
        o = self.criar()
        r = self.client.get(reverse("documentos:editor_embutido", args=["oficio", o.pk]))
        self.assertContains(r, 'data-de-paginas="' + reverse("documentos:editor_paginas", args=["oficio", o.pk]) + '"')
        self.assertContains(r, 'data-de-paginas-texto')

    def test_sem_motor_o_endpoint_diz_indisponivel(self):
        from documentos.services.exceptions import DocumentRendererUnavailable
        o = self.criar()
        with mock.patch("documentos.services.pdf_renderer._weasyprint", side_effect=DocumentRendererUnavailable("sem GTK")):
            r = self.client.get(reverse("documentos:editor_paginas", args=["oficio", o.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": False, "indisponivel": True})

    @skipUnless(weasyprint_disponivel(), "WeasyPrint sem runtime nativo nesta máquina")
    def test_mede_as_paginas_e_a_letra_reduzida_com_cache(self):
        from django.core.cache import cache

        from documentos.services.pdf_renderer import medir_paginas
        cache.clear()
        o = self.criar()
        r = self.client.get(reverse("documentos:editor_paginas", args=["oficio", o.pk]))
        self.assertEqual(r.status_code, 200, r.content)
        dados = r.json()
        self.assertTrue(dados["ok"])
        self.assertEqual(dados["paginas"], 1)
        self.assertTrue(dados["cabe_em_uma"])
        self.assertIn(dados["reduzida"], (0, 1, 2))
        # A segunda chamada com o mesmo documento sai do cache, sem medir de novo.
        with mock.patch("documentos.services.pdf_renderer.medir_paginas", wraps=medir_paginas) as medir_real:
            r2 = self.client.get(reverse("documentos:editor_paginas", args=["oficio", o.pk]))
        self.assertEqual(r2.json(), dados)
        self.assertFalse(medir_real.called)
        # Um motivo enorme passa de uma página mesmo depois dos degraus de compactação.
        type(o).objects.filter(pk=o.pk).update(motivo="Texto longo. " * 900)
        cache.clear()
        dados = self.client.get(reverse("documentos:editor_paginas", args=["oficio", o.pk])).json()
        self.assertGreater(dados["paginas"], 1)
        self.assertEqual(dados["reduzida"], 2)
