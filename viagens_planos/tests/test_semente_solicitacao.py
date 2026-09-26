"""m072: o PT da viagem que veio de solicitação nasce com o que a DG deferiu."""

from datetime import date

from django.test import TestCase

from cadastros.models import Equipe, Servico, TipoEvento, UnidadeMovel
from solicitacoes.models import SolicitacaoEvento
from viagens_oficios.models import Oficio
from viagens_planos.services import TEXTO_UNIDADE_MOVEL, criar_plano_rascunho
from viagens_roteiros.models import Roteiro
from viagens_viagem.models import EquipePrevista, Viagem

from .fixtures import CenarioPlanoMixin


class PlanoDaSolicitacaoTests(CenarioPlanoMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.tipo_evento = TipoEvento.objects.get_or_create(nome="Paraná em Ação")[0]
        self.solicitacao = SolicitacaoEvento.objects.create(
            municipio=self.maringa, data_inicio_evento=date(2026, 6, 25),
            tipo_evento=self.tipo_evento, unidade_movel=True,
            unidade_movel_designada=UnidadeMovel.objects.create(nome="Ônibus 02"),
            criado_por=self.user,
        )
        # Grafia diferente da atividade: a comparação ignora caixa e acento.
        self.solicitacao.itens_servico.create(servico=Servico.objects.get_or_create(nome="EMISSAO DE CIN")[0])
        self.solicitacao.itens_servico.create(servico=Servico.objects.create(nome="Palestra sem par no PT"))
        self.viagem = Viagem.objects.create(
            titulo="Maringá — 25/06/2026", destino_estado=self.uf, destino_municipio=self.maringa,
            data_inicio=date(2026, 6, 25), data_fim=date(2026, 6, 25),
        )
        Roteiro.objects.create(viagem=self.viagem, solicitacao=self.solicitacao, tipo=Roteiro.Tipo.EVENTO)
        self.equipe = Equipe.objects.create(nome="ASCOM")
        EquipePrevista.objects.create(viagem=self.viagem, equipe=self.equipe, quantidade=3)

    def test_atividades_programa_e_unidade_movel_vem_da_solicitacao(self):
        plano = criar_plano_rascunho(viagem=self.viagem)
        self.assertEqual(
            set(plano.atividades_selecionadas.all()), {self.atividade_cin, self.atividade_movel}
        )
        self.assertIn("Emitir carteiras de identidade.", plano.metas)
        self.assertEqual(plano.programa, self.programa)
        self.assertEqual(plano.programa_outros, "")
        self.assertIn(TEXTO_UNIDADE_MOVEL, plano.unidade_movel_texto)
        self.assertIn("Ônibus 02", plano.unidade_movel_texto)

    def test_efetivo_das_equipes_designadas_com_cargo_padrao(self):
        self.cargo_policial.is_padrao = True
        self.cargo_policial.save()
        plano = criar_plano_rascunho(viagem=self.viagem)
        efetivo = plano.efetivos.get()
        self.assertEqual((efetivo.unidade, efetivo.cargo, efetivo.quantidade), (self.ascom, self.cargo_policial, 3))

    def test_sem_cargo_padrao_o_efetivo_fica_para_a_pessoa(self):
        plano = criar_plano_rascunho(viagem=self.viagem)
        self.assertFalse(plano.efetivos.exists())

    def test_efetivo_dos_oficios_quando_ja_existem(self):
        oficio = Oficio.objects.create(viagem=self.viagem, motivo="Evento")
        oficio.servidores.add(self.juliana, self.chefia)
        plano = criar_plano_rascunho(viagem=self.viagem)
        self.assertEqual(plano.total_efetivo, 2)

    def test_sem_programa_cadastrado_usa_o_tipo_de_evento(self):
        self.programa.delete()
        plano = criar_plano_rascunho(viagem=self.viagem)
        self.assertIsNone(plano.programa)
        self.assertEqual(plano.programa_outros, "Paraná em Ação")

    def test_viagem_sem_solicitacao_continua_como_antes(self):
        avulsa = Viagem.objects.create(titulo="Avulsa", destino_estado=self.uf, destino_municipio=self.maringa)
        plano = criar_plano_rascunho(viagem=avulsa)
        self.assertEqual(plano.programa_outros, "Avulsa")
        self.assertFalse(plano.atividades_selecionadas.exists())
