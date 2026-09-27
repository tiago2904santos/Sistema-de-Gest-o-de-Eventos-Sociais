"""m103: "Sugerir texto" na conclusão e nas medidas do RT — regra local, nunca grava."""
from __future__ import annotations

from datetime import datetime, timedelta

from django.urls import reverse
from django.utils import timezone

from auditoria.models import LogAuditoria
from cadastros.models import Estado, Municipio, Regiao
from viagens_planos.models import AtividadePlanoTrabalho, PlanoTrabalho, ResultadoAtividade
from viagens_prestacoes.models import RelatorioTecnico
from viagens_prestacoes.rt_services import sugerir_texto_rt
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin, PrestacaoTestCase as TestCase
from viagens_roteiros.models import RoteiroDestino
from viagens_viagem.models import Viagem


class SugerirTextoRtTests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=103, trechos_roteiro=1)
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        uf = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        regiao = Regiao.objects.get_or_create(nome="Interior")[0]
        cidade = Municipio.objects.get_or_create(codigo_ibge=4113700, defaults={"nome": "Londrina", "estado": uf, "regiao": regiao})[0]
        RoteiroDestino.objects.create(roteiro=self.fixture.roteiro, municipio=cidade, ordem=0)
        saida = timezone.make_aware(datetime(2026, 9, 10, 8))
        self.fixture.roteiro.saida_dt = saida
        self.fixture.roteiro.retorno_chegada_dt = saida + timedelta(days=2)
        self.fixture.roteiro.save()

    def _com_plano(self):
        viagem = Viagem.objects.create(titulo="Paraná em Ação — Londrina")
        oficio = self.prestacao.oficio
        oficio.viagem = viagem
        oficio.save(update_fields=["viagem"])
        plano = PlanoTrabalho.objects.create(viagem=viagem)
        cin = AtividadePlanoTrabalho.objects.create(codigo="M103_CIN", nome="Emissão de CIN", meta="Emitir.")
        orientacao = AtividadePlanoTrabalho.objects.create(codigo="M103_ORI", nome="Orientação jurídica", meta="Orientar.")
        plano.atividades_selecionadas.add(cin, orientacao)
        ResultadoAtividade.objects.create(plano=plano, atividade=cin, realizado=45)
        return plano

    def test_conclusao_usa_evento_destino_periodo_e_resultados_do_plano(self):
        self._com_plano()
        texto = sugerir_texto_rt(self.prestacao, "conclusao")
        self.assertIn("A participação no evento “Paraná em Ação — Londrina”", texto)
        self.assertIn("em Londrina/PR, no período de 10/09 a 12/09/2026", texto)
        self.assertIn("Foram realizados: Emissão de CIN: 45.", texto)
        self.assertTrue(texto.endswith("Não houve intercorrências que comprometessem os resultados."))

    def test_sem_viagem_usa_o_motivo_do_oficio_e_o_objetivo_escrito(self):
        oficio = self.prestacao.oficio
        oficio.motivo = "Diligências na comarca"
        oficio.save(update_fields=["motivo"])
        texto = sugerir_texto_rt(self.prestacao, "conclusao", rascunho={"atividade": "Ouvir as testemunhas"})
        self.assertIn("A viagem para diligências na comarca, em Londrina/PR", texto)
        self.assertIn("O objetivo da participação — Ouvir as testemunhas — foi atingido.", texto)

    def test_medidas_consideram_as_atividades_e_a_pendencia_da_conclusao(self):
        self._com_plano()
        texto = sugerir_texto_rt(self.prestacao, "medidas", rascunho={"conclusao": "Ficou pendente a entrega de dois documentos."})
        self.assertTrue(texto.startswith("Recomenda-se ao órgão: registrar e divulgar internamente os resultados do evento"))
        self.assertIn("(Emissão de CIN e Orientação jurídica)", texto)
        self.assertIn("acompanhar a pendência apontada na conclusão", texto)
        self.assertIn("novas ações em Londrina/PR", texto)

    def test_campo_sem_sugestao_e_recusado(self):
        with self.assertRaises(ValueError):
            sugerir_texto_rt(self.prestacao, "motivo")

    def test_endpoint_devolve_o_texto_sem_gravar_e_registra_na_auditoria(self):
        RelatorioTecnico.objects.create(prestacao=self.prestacao, conclusao="Minha conclusão")
        url = reverse("viagens_prestacoes:rt_servidor_sugerir", args=[self.ps.pk, "conclusao"])
        resposta = self.client.post(url, {"atividade": "Objetivo digitado agora"})
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertTrue(dados["ok"])
        self.assertEqual(dados["campo"], "conclusao")
        self.assertIn("Objetivo digitado agora", dados["texto"])
        self.assertEqual(RelatorioTecnico.objects.get(prestacao=self.prestacao).conclusao, "Minha conclusão")
        self.assertTrue(LogAuditoria.objects.filter(acao="rt_texto_sugerido", usuario=self.user).exists())

    def test_endpoint_recusa_campo_invalido_e_get(self):
        url = reverse("viagens_prestacoes:rt_servidor_sugerir", args=[self.ps.pk, "motivo"])
        self.assertEqual(self.client.post(url).status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_botao_aparece_so_na_conclusao_e_nas_medidas(self):
        resposta = self.client.get(reverse("viagens_prestacoes:rt_servidor", args=[self.ps.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'data-rt-sugerir="conclusao"')
        self.assertContains(resposta, 'data-rt-sugerir="medidas"')
        self.assertNotContains(resposta, 'data-rt-sugerir="motivo"')
        self.assertContains(resposta, reverse("viagens_prestacoes:rt_servidor_sugerir", args=[self.ps.pk, "medidas"]))
