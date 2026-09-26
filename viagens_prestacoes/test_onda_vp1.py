"""Onda V-P1 da prestação de contas (m080–m094): regressões de cada item."""

from __future__ import annotations

import io

from django.test import SimpleTestCase


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
