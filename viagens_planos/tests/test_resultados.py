"""m073: resultados do Plano de Trabalho, relatório final e sugestão para o RT."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from viagens_oficios.models import Oficio
from viagens_planos.models import ResultadoAtividade
from viagens_planos.resultados import (
    linhas_de_resultado,
    salvar_resultados,
    sugestao_para_rt,
    texto_do_relatorio,
)
from viagens_viagem.models import Viagem

from .fixtures import CenarioPlanoMixin


class ResultadosDoPlanoTests(CenarioPlanoMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.viagem = Viagem.objects.create(
            titulo="Maringá", destino_estado=self.uf, destino_municipio=self.maringa,
            data_inicio=date(2026, 6, 25), data_fim=date(2026, 6, 25),
        )
        self.plano = self.criar_plano_maringa()
        self.plano.viagem = self.viagem
        self.plano.programa = self.programa
        self.plano.consideracao_final = "A ação reforça o compromisso institucional."
        self.plano.save()
        self.plano.atividades_selecionadas.set([self.atividade_cin, self.atividade_movel])

    def test_salvar_e_listar_resultados(self):
        erros = salvar_resultados(self.plano, {
            self.atividade_cin.pk: ("120", "RGs emitidos"),
            self.atividade_movel.pk: ("", ""),
        })
        self.assertEqual(erros, [])
        linhas = {l["atividade"].pk: l for l in linhas_de_resultado(self.plano)}
        self.assertEqual(linhas[self.atividade_cin.pk]["realizado"], 120)
        self.assertIsNone(linhas[self.atividade_movel.pk]["realizado"])
        self.assertEqual(ResultadoAtividade.objects.count(), 1)

    def test_numero_invalido_volta_como_erro_e_linha_vazia_apaga(self):
        salvar_resultados(self.plano, {self.atividade_cin.pk: ("10", "")})
        erros = salvar_resultados(self.plano, {self.atividade_movel.pk: ("dez", "")})
        self.assertEqual(len(erros), 1)
        salvar_resultados(self.plano, {self.atividade_cin.pk: ("", "")})
        self.assertFalse(ResultadoAtividade.objects.exists())

    def test_relatorio_final_e_sugestao_para_o_rt(self):
        salvar_resultados(self.plano, {self.atividade_cin.pk: ("120", "RGs emitidos")})
        relatorio = texto_do_relatorio(self.plano)
        self.assertIn("Emissão de CIN: 120 (RGs emitidos)", relatorio)
        self.assertIn("A ação reforça o compromisso institucional.", relatorio)

        oficio = Oficio.objects.create(viagem=self.viagem, motivo="Evento")
        sugestao = sugestao_para_rt(oficio)
        self.assertIn("Emissão de CIN", sugestao["atividade"])
        self.assertIn("Foram realizados: Emissão de CIN: 120.", sugestao["conclusao"])
        self.assertIn("compromisso institucional", sugestao["conclusao"])

    def test_oficio_de_viagem_sem_resultados_nao_sugere(self):
        self.assertEqual(sugestao_para_rt(Oficio.objects.create(viagem=self.viagem, motivo="x")), {})
        self.assertEqual(sugestao_para_rt(Oficio.objects.create(motivo="avulso")), {})

    def test_tela_de_resultados(self):
        url = reverse("viagens_planos:resultados", args=[self.plano.pk])
        editar = self.client.get(reverse("viagens_planos:editar", args=[self.plano.pk]))
        self.assertContains(editar, url)
        resposta = self.client.post(url, {
            f"realizado_{self.atividade_cin.pk}": "80", f"observacao_{self.atividade_cin.pk}": "",
        }, follow=True)
        self.assertContains(resposta, "Resultados salvos.")
        self.assertContains(resposta, "data-relatorio-final")
        self.assertEqual(ResultadoAtividade.objects.get().realizado, 80)
