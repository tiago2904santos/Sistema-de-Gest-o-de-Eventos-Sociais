"""Bordas públicas: expiração, revogação e tokens inválidos têm o mesmo contrato 410."""
from __future__ import annotations
import base64
from datetime import timedelta
from io import BytesIO
from unittest import mock
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from django.utils import timezone
from viagens_cadastros.models import Cargo
from viagens_cadastros.models import Servidor
from viagens_oficios.models import Oficio
from viagens_prestacoes import assinatura_services as svc
from viagens_prestacoes.models import AssinaturaDocumento
from viagens_prestacoes.models import PrestacaoContas

def _pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 700, 'Origem')
    c.showPage()
    c.save()
    return buf.getvalue()

def _png() -> str:
    from PIL import Image, ImageDraw
    buf = BytesIO()
    img = Image.new('RGBA', (120, 40), (0, 0, 0, 0))
    ImageDraw.Draw(img).line((10, 30, 100, 10), fill='black', width=3)
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

class AssinaturaPublicaBordasTests(TestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.cargo = Cargo.objects.create(nome='Agente')
        self.servidor = Servidor.objects.create(nome='Servidor RT', cargo=self.cargo, cpf='11122233344')
        self.oficio = Oficio.objects.create(numero=10, ano=2026, protocolo='123456789')
        self.oficio.servidores.add(self.servidor)
        self.prestacao = PrestacaoContas.objects.get(oficio=self.oficio)
        self.ps = self.prestacao.servidores_prestacao.get(servidor=self.servidor)

    def emitir(self):
        with mock.patch.object(svc, '_origem_rt_bytes', return_value=_pdf()):
            token, docs = svc.emitir_link_rt(self.ps)
        return (token, docs[0])

    def landing(self, token):
        return self.client.get(reverse('viagens_assinaturas:assinatura_landing', args=[token]))

    def validar_identidade(self, token, tipo='rt', cpf='11122'):
        return self.client.post(reverse('viagens_assinaturas:assinatura_identidade', args=[token, tipo]), {'cpf': cpf, 'confirma_nome': 'on'})

    def test_link_expirado_nao_abre_a_landing(self):
        token, doc = self.emitir()
        self.assertEqual(self.landing(token).status_code, 200)
        AssinaturaDocumento.objects.filter(pk=doc.pk).update(link_expira_em=timezone.now() - timedelta(seconds=1))
        response = self.landing(token)
        self.assertEqual(response.status_code, 410)

    def test_link_expirado_nao_serve_o_pdf_de_origem(self):
        """A expiração bloqueia o PDF mesmo após confirmar a identidade."""
        token, doc = self.emitir()
        self.validar_identidade(token)
        pdf_url = reverse('viagens_assinaturas:assinatura_pdf_origem', args=[token, 'rt'])
        self.assertEqual(self.client.get(pdf_url).status_code, 200)
        AssinaturaDocumento.objects.filter(pk=doc.pk).update(link_expira_em=timezone.now() - timedelta(seconds=1))
        response = self.client.get(pdf_url)
        self.assertEqual(response.status_code, 410)

    def test_link_expirado_recusa_a_assinatura(self):
        token, doc = self.emitir()
        self.validar_identidade(token)
        AssinaturaDocumento.objects.filter(pk=doc.pk).update(link_expira_em=timezone.now() - timedelta(seconds=1))
        self.client.post(reverse('viagens_assinaturas:assinatura_assinar', args=[token, 'rt']), {'assinatura_png': _png(), 'modo': 'fonte', 'fonte': 'classica', 'pagina': '0', 'pos_x': '0.5', 'pos_y': '0.7', 'largura': '0.3', 'altura': '0.1'})
        doc.refresh_from_db()
        self.assertNotEqual(doc.status, AssinaturaDocumento.STATUS_ASSINADA)

    def test_token_inexistente_responde_410(self):
        """410 Gone, o mesmo do expirado — não revela se o token já existiu."""
        response = self.landing('token-que-nunca-existiu')
        self.assertEqual(response.status_code, 410)

    def test_token_adulterado_em_um_caractere_nao_abre(self):
        """O token é conferido por inteiro — não basta o prefixo."""
        token, _doc = self.emitir()
        adulterado = token[:-1] + ('a' if token[-1] != 'a' else 'b')
        response = self.landing(adulterado)
        self.assertEqual(response.status_code, 410)

    def test_cancelar_invalida_o_link_ja_emitido(self):
        token, _doc = self.emitir()
        self.assertEqual(self.landing(token).status_code, 200)
        svc.cancelar_assinatura_rt(self.ps)
        self.assertEqual(self.landing(token).status_code, 410)

    def test_tipo_ausente_no_link_nao_e_servido(self):
        """O link de RT não dá acesso ao diário de bordo."""
        token, _doc = self.emitir()
        response = self.client.get(reverse('viagens_assinaturas:assinatura_pdf_origem', args=[token, 'db']))
        self.assertEqual(response.status_code, 410)

    def test_documento_assinado_nao_e_assinado_de_novo(self):
        """Reenviar não sobrescreve: o hash e o código de verificação ficam."""
        token, doc = self.emitir()
        self.validar_identidade(token)
        assinar_url = reverse('viagens_assinaturas:assinatura_assinar', args=[token, 'rt'])
        dados = {'assinatura_png': _png(), 'modo': 'fonte', 'fonte': 'classica', 'pagina': '0', 'pos_x': '0.5', 'pos_y': '0.7', 'largura': '0.3', 'altura': '0.1'}
        self.client.post(assinar_url, dados)
        doc.refresh_from_db()
        self.assertEqual(doc.status, AssinaturaDocumento.STATUS_ASSINADA)
        hash_original = doc.hash_documento
        codigo_original = doc.codigo_verificacao
        self.client.post(assinar_url, dados)
        doc.refresh_from_db()
        self.assertEqual(doc.hash_documento, hash_original)
        self.assertEqual(doc.codigo_verificacao, codigo_original)
