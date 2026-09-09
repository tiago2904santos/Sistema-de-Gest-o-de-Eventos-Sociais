"""Fixtures F5: módulo VIAGENS real, banco isolado e documentos válidos."""
import io
import tempfile
from dataclasses import dataclass
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from django.test import TestCase as DjangoTestCase, override_settings
from accounts.models import Modulo, Setor
from viagens_cadastros.models import Cargo, Servidor
from viagens_oficios.models import Oficio
from viagens_prestacoes.models import PrestacaoContas
from viagens_roteiros.models import Roteiro, RoteiroTrecho


class PrestacaoTestCase(DjangoTestCase):
    """Mesmo com `manage.py test`, nenhum arquivo da fixture vai ao media de dev."""
    @classmethod
    def setUpClass(cls):
        pasta = tempfile.TemporaryDirectory(prefix='f5-fixture-media-')
        cls.addClassCleanup(pasta.cleanup)
        config = override_settings(MEDIA_ROOT=pasta.name)
        config.enable()
        cls.addClassCleanup(config.disable)
        super().setUpClass()


def autorizar_viagens(usuario):
    modulo = Modulo.objects.get(codigo="VIAGENS")
    setor, _ = Setor.objects.get_or_create(nome="Setor de validação F5", defaults={"sigla": "F5"})
    setor.modulos.add(modulo)
    usuario.setores.add(setor)
    usuario.groups.add(Group.objects.get(name="VIAGENS_OPERADOR"))


def imagem_bytes(formato="PNG"):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1,1), color="white").save(buf, format=formato)
    return buf.getvalue()


def pdf_minimo(texto="Documento de teste"):
    from reportlab.pdfgen import canvas
    buf = io.BytesIO(); c = canvas.Canvas(buf)
    c.drawString(50, 750, texto); c.save()
    return buf.getvalue()

PDF_MINIMO = pdf_minimo()

@dataclass(frozen=True)
class PrestacaoFixture:
    oficio: Oficio
    prestacao: PrestacaoContas
    servidores: tuple
    prestacoes_servidor: tuple
    roteiro: Roteiro | None


class PrestacaoFixturesMixin:
    def setUpPrestacaoFixtures(self):
        self.user = get_user_model().objects.create_user(username="tester_prestacao", password="123456")
        autorizar_viagens(self.user)
        self.client.force_login(self.user)
        self._cpf_sequence = 0

    def criar_servidor(self, nome):
        cargo, _ = Cargo.objects.get_or_create(nome="AGENTE")
        self._cpf_sequence += 1
        return Servidor.objects.create(nome=nome, cargo=cargo, cpf=f"{self._cpf_sequence:011d}")

    def criar_prestacao(self, *, numero, ano=2026, servidor=None, servidores=None, status="pendente", data_liberacao_diarias=None, arquivada=False, finalizada=False, cancelado=False, criado_em=None, com_roteiro=True, trechos_roteiro=1):
        servidores = tuple(servidores) if servidores is not None else (servidor or self.criar_servidor(f"Servidor {numero}"),)
        roteiro = Roteiro.objects.create() if com_roteiro else None
        if roteiro:
            for ordem in range(trechos_roteiro):
                RoteiroTrecho.objects.create(roteiro=roteiro, sentido=RoteiroTrecho.Sentido.IDA, ordem=ordem)
        oficio = Oficio.objects.create(numero=numero, ano=ano, protocolo=f"{ano}{numero:05d}", roteiro=roteiro)
        oficio.servidores.add(*servidores)
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        if cancelado:
            Oficio.objects.filter(pk=oficio.pk).update(cancelado=True); oficio.refresh_from_db()
        if criado_em:
            PrestacaoContas.objects.filter(pk=prestacao.pk).update(criado_em=criado_em); prestacao.refresh_from_db()
        por_servidor = {ps.servidor_id: ps for ps in prestacao.servidores_prestacao.all()}
        partes = tuple(por_servidor[s.pk] for s in servidores)
        for ps in partes:
            ps.status=status; ps.data_liberacao_diarias=data_liberacao_diarias; ps.arquivada=arquivada; ps.finalizada=finalizada; ps.save()
        return PrestacaoFixture(oficio=oficio, prestacao=prestacao, servidores=servidores, prestacoes_servidor=partes, roteiro=roteiro)

    def get_listagem(self, **params):
        return self.client.get(reverse("viagens_prestacoes:index"), params)
