"""Cenário das ordens de serviço, no molde de `viagens_oficios/tests/fixtures.py`.

Um operador logado, a configuração com unidade e assinante da OS, dois
municípios, três servidores e um ofício com roteiro Curitiba → Londrina para
vincular. `payload()` é o que a tela envia ao salvar.
"""

import tempfile
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from django.utils import timezone

from accounts.models import Modulo, Setor
from cadastros.models import Estado, Municipio, Regiao
from viagens_cadastros.models import AssinaturaConfiguracao, Cargo, ConfiguracaoSistema, Servidor, Unidade, Viatura
from viagens_oficios.models import Oficio
from viagens_ordens.models import OrdemServico
from viagens_roteiros.models import Roteiro, RoteiroDestino


class CenarioOrdemMixin:
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=pasta.name, DOCUMENTOS_DEFAULT_PDF_ENGINE="simple"))
        self.user = get_user_model().objects.create_user(username="operador-os", deve_trocar_senha=False)
        self.setor = Setor.objects.create(nome="Setor OS")
        Modulo.objects.get(codigo="VIAGENS").setores.add(self.setor)
        self.user.setores.add(self.setor)
        self.user.groups.add(Group.objects.get(name="VIAGENS_OPERADOR"))
        self.client.force_login(self.user)
        regiao = Regiao.objects.get_or_create(nome="Interior")[0]
        self.uf = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        self.sede = Municipio.objects.get_or_create(codigo_ibge=4106902, defaults={"nome": "Curitiba", "estado": self.uf, "regiao": regiao})[0]
        self.destino = Municipio.objects.get_or_create(codigo_ibge=4113700, defaults={"nome": "Londrina", "estado": self.uf, "regiao": regiao})[0]
        self.outro = Municipio.objects.get_or_create(codigo_ibge=4115200, defaults={"nome": "Maringá", "estado": self.uf, "regiao": regiao})[0]
        self.cargo = Cargo.objects.create(nome="Investigador")
        self.unidade = Unidade.objects.create(nome="Unidade OS")
        self.a = Servidor.objects.create(nome="ANA TESTE", cargo=self.cargo, unidade=self.unidade, cpf="11122233344")
        self.b = Servidor.objects.create(nome="BRUNO TESTE", cargo=self.cargo, unidade=self.unidade, cpf="55566677788")
        self.c = Servidor.objects.create(nome="CARLA TESTE", cargo=self.cargo, unidade=self.unidade, cpf="99988877766")
        self.viatura = Viatura.objects.create(placa="ABC1D23", modelo="VEÍCULO OS")
        self.cfg = ConfiguracaoSistema.get_singleton()
        self.cfg.unidade = self.unidade
        self.cfg.save()
        AssinaturaConfiguracao.objects.create(configuracao=self.cfg, tipo=AssinaturaConfiguracao.ORDEM_SERVICO, servidor=self.b)
        self.hoje = timezone.localdate()

    def oficio(self, *, dias=3, servidores=(), motorista=None, motivo="Missão do ofício", protocolo="123456789", cancelar=False):
        saida = timezone.make_aware(datetime.combine(self.hoje + timedelta(days=dias), datetime.min.time().replace(hour=8)))
        roteiro = Roteiro.objects.create(origem_municipio=self.sede, saida_dt=saida, retorno_chegada_dt=saida + timedelta(hours=30))
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.destino)
        oficio = Oficio.objects.create(numero=Oficio.objects.count() + 1, ano=self.hoje.year, protocolo=protocolo, motivo=motivo,
                                       roteiro=roteiro, viatura=self.viatura, motorista=motorista)
        oficio.servidores.set(servidores)
        if cancelar:
            oficio.cancelar("Adiado")
        return oficio

    def ordem(self, *, tipo=OrdemServico.TIPO_PADRAO, dias=3, destinos=None, servidores=(), oficios=(), motivo="Apoio ao evento", funcoes=None, cancelar=False):
        inicio = self.hoje + timedelta(days=dias) if dias is not None else None
        ordem = OrdemServico.objects.create(tipo_necessidade=tipo, data_evento_inicio=inicio, data_evento_fim=inicio + timedelta(days=1) if inicio else None,
                                            motivo=motivo, funcoes_servidores=funcoes or {})
        ordem.destinos.set([self.destino] if destinos is None else destinos)
        ordem.servidores.set(servidores)
        ordem.oficios.set(oficios)
        if cancelar:
            ordem.cancelar("Adiado")
        return ordem

    def payload(self, **extra):
        dados = {
            "tipo_necessidade": OrdemServico.TIPO_PADRAO, "motivo": "Cobertura do evento institucional",
            "data_evento_inicio": (self.hoje + timedelta(days=5)).isoformat(), "data_evento_fim": (self.hoje + timedelta(days=6)).isoformat(),
            "quantidade_destinos": "0", "destino_estado": str(self.uf.pk), "destino_cidade": str(self.destino.pk),
            "servidores": [str(self.a.pk), str(self.b.pk)],
        }
        dados.update(extra)
        return dados
