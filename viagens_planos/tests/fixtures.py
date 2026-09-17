"""Cenário dos testes de planos de trabalho, no molde do dos ofícios.

Um operador logado, a configuração com sede em Curitiba, unidade ASCOM e o
assinante do plano, a tabela de diárias vigente (o interior a R$ 290,55, que
reproduz os planos reais 20/2026 e 18/2026 da origem), cargos e servidores.
`criar_plano_maringa()` grava o plano do exemplo real de Maringá.
"""

import tempfile
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from django.urls import reverse

from accounts.models import Modulo, Setor
from cadastros.models import Estado, Municipio, Regiao
from viagens_cadastros.models import AssinaturaConfiguracao, Cargo, ConfiguracaoSistema, Servidor, TabelaDiaria, Unidade
from viagens_planos.models import AtividadePlanoTrabalho, EfetivoPlano, PlanoTrabalho, PresetAtividadesPlanoTrabalho, ProgramaSolicitante

UNIDADE_ASCOM_NOME = "ASSESSORIA DE COMUNICAÇÃO SOCIAL"


class CenarioPlanoMixin:
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=pasta.name, DOCUMENTOS_DEFAULT_PDF_ENGINE="simple"))
        self.user = get_user_model().objects.create_user(username="operador-pt", deve_trocar_senha=False)
        self.setor = Setor.objects.create(nome="Setor PT")
        Modulo.objects.get(codigo="VIAGENS").setores.add(self.setor)
        self.user.setores.add(self.setor)
        self.user.groups.add(Group.objects.get(name="VIAGENS_OPERADOR"))
        self.client.force_login(self.user)

        self.uf = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        interior = Regiao.objects.get_or_create(nome="Interior")[0]
        self.curitiba = Municipio.objects.get_or_create(codigo_ibge=4106902, defaults={"nome": "Curitiba", "estado": self.uf, "regiao": Regiao.objects.get_or_create(nome="Capital")[0], "capital": True})[0]
        self.maringa = Municipio.objects.get_or_create(codigo_ibge=4115200, defaults={"nome": "Maringá", "estado": self.uf, "regiao": interior})[0]
        self.sarandi = Municipio.objects.get_or_create(codigo_ibge=4126256, defaults={"nome": "Sarandi", "estado": self.uf, "regiao": interior})[0]
        self.londrina = Municipio.objects.get_or_create(codigo_ibge=4113700, defaults={"nome": "Londrina", "estado": self.uf, "regiao": interior})[0]

        for faixa, valor in ((TabelaDiaria.Faixa.INTERIOR, "290.55"), (TabelaDiaria.Faixa.CAPITAL, "350.00"), (TabelaDiaria.Faixa.BRASILIA, "400.00")):
            TabelaDiaria.objects.create(faixa=faixa, vigencia_inicio=date(2026, 1, 1), valor_24h=Decimal(valor))

        self.ascom = Unidade.objects.create(nome=UNIDADE_ASCOM_NOME, sigla="ASCOM")
        self.cargo_policial = Cargo.objects.create(nome="Policial Civil")
        self.cargo_papiloscopista = Cargo.objects.create(nome="Papiloscopista")
        cargo_assessor = Cargo.objects.create(nome="Assessor de Comunicação Social")
        self.chefia = Servidor.objects.create(nome="João Mário Nunes de Góes", cpf="98765432100", cargo=cargo_assessor, unidade=self.ascom)
        self.juliana = Servidor.objects.create(nome="Juliana Villela de Barros", cpf="11122233344", cargo=self.cargo_papiloscopista, unidade=self.ascom)

        self.cfg = ConfiguracaoSistema.get_singleton()
        self.cfg.cidade_sede_padrao = self.curitiba
        self.cfg.unidade = self.ascom
        self.cfg.cidade_endereco = "Curitiba"
        self.cfg.uf = "PR"
        self.cfg.nome_chefia = "João Mário Nunes de Góes"
        self.cfg.cargo_chefia = "Assessor de Comunicação Social"
        self.cfg.pt_sufixo_numero = "ASCOM"
        self.cfg.save()
        AssinaturaConfiguracao.objects.create(configuracao=self.cfg, tipo=AssinaturaConfiguracao.PLANO_TRABALHO, servidor=self.chefia, ordem=1)

        self.programa = ProgramaSolicitante.objects.get_or_create(nome="PROGRAMA PARANÁ EM AÇÃO")[0]
        # O catálogo semeado pela migração sai: os testes conferem metas e recursos próprios.
        AtividadePlanoTrabalho.objects.all().delete()
        self.atividade_cin = AtividadePlanoTrabalho.objects.create(codigo="CIN", nome="Emissão de CIN", meta="Emitir carteiras de identidade.", recurso_necessario="Kit de coleta biométrica.")
        self.atividade_movel = AtividadePlanoTrabalho.objects.create(codigo="UNIDADE_MOVEL", nome="Unidade móvel", meta="Levar a estrutura móvel.", recurso_necessario="")
        self.preset = PresetAtividadesPlanoTrabalho.objects.create(nome="PCPR na Comunidade", is_padrao=True)
        self.preset.atividades.set([self.atividade_cin])

    def criar_plano_maringa(self, *, efetivo=6):
        """O plano 20/2026 de Maringá: 4 pernoites + 7 h de resto → 4 x 100% + 1 x 15%."""
        plano = PlanoTrabalho.objects.create(
            numero=20, ano=2026, sufixo_numero="ASCOM",
            destino_estado=self.uf, destino_cidade=self.maringa,
            data_evento_inicio=date(2026, 6, 25), data_evento_fim=date(2026, 6, 27),
            saida_sede_data=date(2026, 6, 24), saida_sede_hora=time(7, 0),
            chegada_sede_data=date(2026, 6, 28), chegada_sede_hora=time(14, 0),
        )
        EfetivoPlano.objects.create(plano=plano, unidade=self.ascom, cargo=self.cargo_policial, quantidade=efetivo)
        return plano

    def payload(self, **extra):
        """O que a tela envia ao clicar em "Salvar plano", no plano de Maringá."""
        dados = {
            "programa": str(self.programa.pk), "programa_outros": "",
            "destino_estado": str(self.uf.pk), "destino_cidade": str(self.maringa.pk), "quantidade_destinos": "0",
            "data_evento_inicio": "2026-06-25", "data_evento_fim": "2026-06-27", "horario_atendimento": "09:00 até 17:00",
            "coordenador_adm_modo": "SERVIDOR", "coordenador_adm": str(self.juliana.pk), "coordenador_adm_nome_manual": "",
            "coordenador_adm_cargo_manual": "", "coordenador_adm_genero": "FEMININO",
            "coordenador_op_modo": "MANUAL", "coordenador_op": "", "coordenador_op_nome_manual": "José Pereira",
            "coordenador_op_cargo_manual": "Policial Civil", "coordenador_op_genero": "MASCULINO",
            "contextualizacao": "", "coordenacao": "", "consideracao_final": "",
            "contextualizacao_auto": "1", "coordenacao_auto": "1", "consideracao_auto": "1",
            "efetivo-TOTAL_FORMS": "1", "efetivo-INITIAL_FORMS": "0", "efetivo-MIN_NUM_FORMS": "1", "efetivo-MAX_NUM_FORMS": "1000",
            "efetivo-0-id": "", "efetivo-0-unidade": str(self.ascom.pk), "efetivo-0-cargo": str(self.cargo_policial.pk), "efetivo-0-quantidade": "6",
            "saida_sede_data": "2026-06-24", "saida_sede_hora": "07:00", "chegada_sede_data": "2026-06-28", "chegada_sede_hora": "14:00",
            "atividades_codigos": ["CIN"],
            "acao": "salvar",
        }
        dados.update(extra)
        return dados

    def payload_vazio(self, **extra):
        """A mesma tela com a identificação em branco — como ela volta depois de "Adicionar evento"."""
        base = {
            "programa": "", "destino_estado": "", "destino_cidade": "",
            "data_evento_inicio": "", "data_evento_fim": "", "atividades_codigos": [],
            "efetivo-TOTAL_FORMS": "0", "efetivo-0-unidade": "", "efetivo-0-cargo": "", "efetivo-0-quantidade": "",
        }
        base.update(extra)
        return self.payload(**base)

    def criar_pela_tela(self):
        resposta = self.client.post(reverse("viagens_planos:criar"))
        self.assertEqual(resposta.status_code, 302)
        return PlanoTrabalho.objects.latest("pk")

    @staticmethod
    def conteudo(resposta):
        return b"".join(resposta.streaming_content) if resposta.streaming else resposta.content
