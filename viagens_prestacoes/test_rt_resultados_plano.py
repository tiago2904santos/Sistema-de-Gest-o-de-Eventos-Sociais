"""m073: o RT da prestação abre com objetivo e conclusão vindos dos resultados do PT."""
from __future__ import annotations

from django.urls import reverse

from viagens_planos.models import AtividadePlanoTrabalho, PlanoTrabalho, ResultadoAtividade
from viagens_prestacoes.models import RelatorioTecnico
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin
from viagens_viagem.models import Viagem

from .test_helpers import PrestacaoTestCase as TestCase


class RtComResultadosDoPlanoTests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=73)
        self.viagem = Viagem.objects.create(titulo="Evento com PT")
        oficio = self.fixture.prestacao.oficio
        oficio.viagem = self.viagem
        oficio.save(update_fields=["viagem"])
        plano = PlanoTrabalho.objects.create(viagem=self.viagem, programa_outros="Paraná em Ação")
        atividade = AtividadePlanoTrabalho.objects.create(codigo="CIN_RT", nome="Emissão de CIN (RT)", meta="Emitir.")
        plano.atividades_selecionadas.add(atividade)
        ResultadoAtividade.objects.create(plano=plano, atividade=atividade, realizado=45)

    def test_campos_vazios_do_rt_vem_sugeridos(self):
        ps = self.fixture.prestacoes_servidor[0]
        resposta = self.client.get(reverse("viagens_prestacoes:rt_servidor", args=[ps.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Foram realizados: Emissão de CIN (RT): 45.")

    def test_texto_ja_digitado_no_rt_nao_e_trocado(self):
        RelatorioTecnico.objects.create(
            prestacao=self.fixture.prestacao, atividade="Objetivo meu", conclusao="Conclusão minha"
        )
        ps = self.fixture.prestacoes_servidor[0]
        resposta = self.client.get(reverse("viagens_prestacoes:rt_servidor", args=[ps.pk]))
        self.assertNotContains(resposta, "Foram realizados")
        self.assertContains(resposta, "Conclusão minha")
