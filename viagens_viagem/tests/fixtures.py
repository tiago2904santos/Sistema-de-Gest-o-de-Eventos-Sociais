"""Cenário das viagens, no molde do de ofícios.

Um operador logado no módulo VIAGENS, a configuração com a sede em Curitiba,
dois servidores, viatura, um tipo de viagem e um modelo de motivo — o mínimo
para o painel abrir com opções e para os documentos nascerem da viagem.
"""
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Modulo, Setor
from cadastros.models import Estado, Municipio, Regiao
from viagens_cadastros.models import Cargo, ConfiguracaoSistema, Servidor, Unidade, Viatura
from viagens_oficios.models import ModeloMotivoOficio
from viagens_viagem.models import TipoViagem, Viagem


class CenarioViagem(TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=pasta.name, DOCUMENTOS_DEFAULT_PDF_ENGINE="simple"))
        self.user = get_user_model().objects.create_user(username="operador-vg", deve_trocar_senha=False)
        self.setor = Setor.objects.create(nome="Setor VG")
        Modulo.objects.get(codigo="VIAGENS").setores.add(self.setor)
        self.user.setores.add(self.setor)
        self.user.groups.add(Group.objects.get(name="VIAGENS_OPERADOR"))
        self.client.force_login(self.user)
        self.pr = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        interior = Regiao.objects.get_or_create(nome="Interior")[0]
        self.sede = Municipio.objects.get_or_create(codigo_ibge=4106902, defaults={"nome": "Curitiba", "estado": self.pr, "regiao": interior})[0]
        self.londrina = Municipio.objects.get_or_create(codigo_ibge=4113700, defaults={"nome": "Londrina", "estado": self.pr, "regiao": interior})[0]
        self.maringa = Municipio.objects.get_or_create(codigo_ibge=4115200, defaults={"nome": "Maringá", "estado": self.pr, "regiao": interior})[0]
        self.cargo = Cargo.objects.create(nome="Investigador")
        self.unidade = Unidade.objects.create(nome="Unidade VG")
        self.a = Servidor.objects.create(nome="ANA VIAGEM", cargo=self.cargo, unidade=self.unidade, cpf="11122233344")
        self.b = Servidor.objects.create(nome="BRUNO VIAGEM", cargo=self.cargo, unidade=self.unidade, cpf="55566677788")
        self.viatura = Viatura.objects.create(placa="ABC1D23", modelo="VEÍCULO VG")
        self.tipo = TipoViagem.objects.get_or_create(nome="PCPR na Comunidade")[0]
        self.modelo = ModeloMotivoOficio.objects.create(nome="Padrão", texto="Texto do modelo.")
        self.cfg = ConfiguracaoSistema.get_singleton()
        self.cfg.unidade = self.unidade
        self.cfg.cidade_sede_padrao = self.sede
        self.cfg.save()

    def viagem(self, **campos):
        dados = {"titulo": "PCPR na Comunidade", "destino_estado": self.pr, "destino_municipio": self.londrina,
                 "data_inicio": date(2026, 10, 5), "data_fim": date(2026, 10, 7), "unidade_responsavel": self.unidade}
        dados.update(campos)
        viagem = Viagem.objects.create(**dados)
        viagem.tipos.add(self.tipo)
        return viagem

    def etapa(self, viagem, n):
        return reverse("viagens_viagem:etapa", args=[viagem.pk, n])

    def payload_etapa1(self, **extras):
        dados = {
            "tipos": [str(self.tipo.pk)], "modelo_motivo": str(self.modelo.pk), "motivo": "Atividade comunitária",
            "data_inicio": "2026-10-05", "data_fim": "2026-10-07",
            "destino_estado": str(self.pr.pk), "destino_municipio": str(self.londrina.pk),
            "quantidade_destinos": "1", "extra_estado_0": str(self.pr.pk), "extra_cidade_0": str(self.maringa.pk),
        }
        dados.update(extras)
        return dados
