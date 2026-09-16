"""Cenário de ofício completo, compartilhado pelos testes do módulo.

Um operador logado, a configuração do sistema com unidade e assinatura, dois
servidores, viatura, roteiro Curitiba → Londrina com um trecho — o mínimo
que passa na validação do documento. `criar()` grava o ofício pela própria
tela, como a pessoa faria.
"""
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Modulo, Setor
from cadastros.models import Estado, Municipio, Regiao
from viagens_cadastros.models import AssinaturaConfiguracao, Cargo, ConfiguracaoSistema, Servidor, Unidade, Viatura
from viagens_oficios.models import Oficio
from viagens_roteiros.models import Roteiro, RoteiroDestino, RoteiroTrecho


class CenarioOficioMixin:
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=folder.name, DOCUMENTOS_DEFAULT_PDF_ENGINE='simple'))
        self.user = get_user_model().objects.create_user(username='operador-f4', deve_trocar_senha=False)
        self.setor = Setor.objects.create(nome='Setor F4')
        Modulo.objects.get(codigo='VIAGENS').setores.add(self.setor)
        self.user.setores.add(self.setor)
        self.user.groups.add(Group.objects.get(name='VIAGENS_OPERADOR'))
        self.client.force_login(self.user)
        self.uf = Estado.objects.get_or_create(sigla='PR', defaults={'nome':'Paraná', 'codigo_ibge':41})[0]
        self.sede = Municipio.objects.get_or_create(codigo_ibge=4106902, defaults={'nome':'Curitiba', 'estado':self.uf, 'regiao':Regiao.objects.get_or_create(nome='Interior')[0]})[0]
        self.destino = Municipio.objects.get_or_create(codigo_ibge=4113700, defaults={'nome':'Londrina', 'estado':self.uf, 'regiao':Regiao.objects.get_or_create(nome='Interior')[0]})[0]
        self.cargo = Cargo.objects.create(nome='Investigador')
        self.unidade = Unidade.objects.create(nome='Unidade F4')
        self.a = Servidor.objects.create(nome='ANA TESTE', cargo=self.cargo, unidade=self.unidade, cpf='11122233344')
        self.b = Servidor.objects.create(nome='BRUNO TESTE', cargo=self.cargo, unidade=self.unidade, cpf='55566677788')
        self.viatura = Viatura.objects.create(placa='ABC1D23', modelo='VEÍCULO F4')
        self.saida = timezone.make_aware(datetime(2026, 9, 10, 8))
        self.roteiro = Roteiro.objects.create(origem_municipio=self.sede, saida_dt=self.saida,
            retorno_chegada_dt=self.saida+timedelta(hours=24), valor_diarias=Decimal('43.58'), resumo_diarias='1 x 100%')
        RoteiroDestino.objects.create(roteiro=self.roteiro, municipio=self.destino)
        RoteiroTrecho.objects.create(roteiro=self.roteiro, origem_municipio=self.sede, destino_municipio=self.destino,
            saida_dt=self.saida, chegada_dt=self.saida+timedelta(hours=4))
        self.cfg = ConfiguracaoSistema.get_singleton()
        self.cfg.unidade = self.unidade
        self.cfg.save()
        AssinaturaConfiguracao.objects.create(configuracao=self.cfg, tipo='OFICIO', servidor=self.b)

    def payload(self):
        return {'data_criacao': '2026-09-09', 'protocolo': '12.345.678-9', 'motivo': 'Missão F4',
                'custeio': 'UNIDADE_DPC', 'servidores': [str(self.a.pk), str(self.b.pk)],
                'servidores_termo_autorizacao': [str(self.a.pk), str(self.b.pk)],
                'viatura': self.viatura.pk, 'motorista': self.a.pk, 'motorista_modo': 'SERVIDOR',
                'roteiro': self.roteiro.pk, 'justificativa-texto': 'Solicitação recebida nesta data.'}

    def criar(self):
        response = self.client.post(reverse('viagens_oficios:novo'), self.payload())
        self.assertEqual(response.status_code, 302, response.content[:2000])
        oficio = Oficio.objects.latest('pk')
        # O cadastro liga o roteiro pelo editor embutido e não mostra a data;
        # o cenário usa o roteiro pronto e a data fixa.
        Oficio.objects.filter(pk=oficio.pk).update(roteiro=self.roteiro, data_criacao=datetime(2026, 9, 9).date())
        oficio.refresh_from_db()
        return oficio
