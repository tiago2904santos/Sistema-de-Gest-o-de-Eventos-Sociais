"""Onda V-P2: hodômetro do diário (m078, m095, m088)."""
from __future__ import annotations

import json
from decimal import Decimal

from django.urls import reverse

from cadastros.models import Estado, Municipio, Regiao
from viagens_prestacoes.models import DiarioBordo
from viagens_roteiros.models import DistanciaMunicipios, Roteiro, RoteiroTrecho

from .test_helpers import PrestacaoFixturesMixin
from .test_helpers import PrestacaoTestCase as TestCase


class HodometroDoDiarioTests(PrestacaoFixturesMixin, TestCase):
    """m078/m095: distância prevista por trecho, sugestão e conferência (aviso, não bloqueio)."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        estado, _ = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})
        regiao, _ = Regiao.objects.get_or_create(nome="Interior")
        self.sede = Municipio.objects.create(nome="Cidade Sede", estado=estado, regiao=regiao)
        self.destino = Municipio.objects.create(nome="Cidade Destino", estado=estado, regiao=regiao)
        self.fixture = self.criar_prestacao(numero=301, com_roteiro=False)
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        roteiro = Roteiro.objects.create()
        RoteiroTrecho.objects.create(
            roteiro=roteiro, sentido=RoteiroTrecho.Sentido.IDA, ordem=0,
            origem_municipio=self.sede, destino_municipio=self.destino, distancia_km=Decimal("100.40"),
        )
        RoteiroTrecho.objects.create(
            roteiro=roteiro, sentido=RoteiroTrecho.Sentido.RETORNO, ordem=1,
            origem_municipio=self.destino, destino_municipio=self.sede,
        )
        self.fixture.oficio.roteiro = roteiro
        self.fixture.oficio.save(update_fields=["roteiro", "atualizado_em"])
        self.diario, _ = DiarioBordo.objects.get_or_create(prestacao=self.prestacao)

    def abrir(self):
        return self.client.get(reverse("viagens_prestacoes:diario_servidor", args=[self.ps.pk]))

    def autosave(self, **campos):
        return self.client.post(
            reverse("viagens_prestacoes:diario_servidor_autosave", args=[self.ps.pk]),
            data=json.dumps({"model": "diario_bordo", "object_id": str(self.diario.pk), "dirty_fields": list(campos), "fields": campos}),
            content_type="application/json",
        )

    def test_distancia_prevista_vem_do_trecho_e_serve_a_volta(self):
        resposta = self.abrir()
        self.assertEqual(resposta.status_code, 200)
        # A ida tem distância no roteiro; a volta, sem distância, usa o mesmo par guardado.
        self.assertEqual([i["prevista"] for i in resposta.context["hodometro"]["linhas"]], [100, 100])
        self.assertContains(resposta, 'data-prevista="100"', count=2)
        self.assertTrue(DistanciaMunicipios.objects.filter(origem=self.sede, destino=self.destino).exists())

    def test_autosave_devolve_totais_e_avisa_sem_bloquear(self):
        self.abrir()
        resposta = self.autosave(**{
            "form-0-km_inicial": "10.000", "form-0-km_final": "10.101",
            "form-1-km_inicial": "10.050", "form-1-km_final": "10.300",
        })
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertTrue(dados["ok"])
        hodometro = dados["hodometro"]
        self.assertEqual(hodometro["total_rodado"], 101 + 250)
        self.assertEqual(hodometro["total_previsto"], 200)
        avisos = " ".join(hodometro["avisos"])
        self.assertIn("voltou para trás", avisos)
        self.assertIn("250 km rodados", avisos)
        # Gravou mesmo com os avisos.
        linhas = list(self.diario.trechos.order_by("ordem"))
        self.assertEqual(linhas[1].km_final, 10300)

    def test_rodado_dentro_da_tolerancia_nao_avisa(self):
        self.abrir()
        dados = self.autosave(**{
            "form-0-km_inicial": "500", "form-0-km_final": "610",
            "form-1-km_inicial": "610", "form-1-km_final": "705",
        }).json()
        self.assertEqual(dados["hodometro"]["avisos"], [])

    def test_corrigir_distancia_pela_linha_vale_para_o_par(self):
        self.abrir()
        linha = self.diario.trechos.order_by("ordem").first()
        resposta = self.client.post(
            reverse("viagens_prestacoes:diario_servidor_distancia", args=[self.ps.pk, linha.pk]),
            {"distancia_km": "120,5"},
        )
        self.assertEqual(resposta.status_code, 302)
        registro = DistanciaMunicipios.objects.get(origem=self.sede, destino=self.destino)
        self.assertEqual(registro.distancia_km, Decimal("120.50"))
        self.assertEqual(registro.fonte, DistanciaMunicipios.Fonte.MANUAL)
        self.assertEqual([i["prevista"] for i in self.abrir().context["hodometro"]["linhas"]], [120, 120])
