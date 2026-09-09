from django.test import TestCase
from viagens_cadastros.models import Cargo
from viagens_cadastros.models import ConfiguracaoSistema
from viagens_cadastros.models import Servidor
from viagens_cadastros.models import Unidade
from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context
from viagens_oficios.models import Oficio

class DestinatarioOficioDocxtplTests(TestCase):

    def setUp(self):
        self.cfg = ConfiguracaoSistema.get_singleton()
        self.cargo = Cargo.objects.create(nome='Delegado-Geral Adjunto Operacional')
        self.unidade = Unidade.objects.create(nome='Gabinete do Delegado Geral Adjunto')

    def test_sem_destinatario_configurado_usa_padrao(self):
        oficio = Oficio.objects.create()
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertEqual(ctx['orgao_destino'], 'Gabinete do Delegado Geral Adjunto')
        self.assertEqual(ctx['nome_destinatario'], '')
        self.assertEqual(ctx['cargo_destinatario'], '')

    def test_destinatario_configurado_alimenta_destino_e_nome_cargo(self):
        destinatario = Servidor.objects.create(nome='Riad Braga Farhat', cargo=self.cargo, unidade=self.unidade)
        self.cfg.destinatario_oficio = destinatario
        self.cfg.save()
        oficio = Oficio.objects.create()
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertEqual(ctx['orgao_destino'], 'Gabinete do Delegado Geral Adjunto')
        self.assertEqual(ctx['nome_destinatario'], 'Riad Braga Farhat')
        self.assertEqual(ctx['cargo_destinatario'], 'Delegado-Geral Adjunto Operacional')

    def test_destinatario_manual_sem_servidor_cadastrado(self):
        self.cfg.destinatario_oficio_nome = 'Maria Souza'
        self.cfg.destinatario_oficio_cargo = 'Diretora'
        self.cfg.destinatario_oficio_unidade = 'Secretaria Executiva'
        self.cfg.save()
        oficio = Oficio.objects.create()
        ctx = build_oficio_docxtpl_context(oficio)
        self.assertEqual(ctx['orgao_destino'], 'Secretaria Executiva')
        self.assertEqual(ctx['nome_destinatario'], 'Maria Souza')
        self.assertEqual(ctx['cargo_destinatario'], 'Diretora')
