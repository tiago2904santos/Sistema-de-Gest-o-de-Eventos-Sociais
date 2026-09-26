"""m078: a distância entre municípios fica guardada e é consultada antes da API."""

from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.urls import reverse

from cadastros.models import Municipio

from .models import DistanciaMunicipios
from .services import distancias, rota
from .tests import BaseTelaRoteiroTestCase


class DistanciasGuardadasTests(BaseTelaRoteiroTestCase):
    def setUp(self):
        self.client.force_login(self.criar_usuario("distancias", "VIAGENS_OPERADOR"))

    def test_estimativa_vem_da_tabela_sem_chave_e_sem_api(self):
        DistanciaMunicipios.objects.create(
            origem=self.sao_paulo, destino=self.curitiba, distancia_km=Decimal("408.00"),
            fonte=DistanciaMunicipios.Fonte.ROTEIRO,
        )
        with self.settings(OPENROUTESERVICE_API_KEY=""):
            # Pedido no sentido inverso: a tabela serve os dois.
            resposta = self.client.post(
                reverse("viagens_roteiros:estimar_trecho"),
                {"origem": self.curitiba.pk, "destino": self.sao_paulo.pk},
            )
        dados = resposta.json()
        self.assertTrue(dados["ok"])
        self.assertEqual(dados["distancia_km"], 408.0)
        self.assertGreater(dados["tempo_viagem_min"], 0)

    def test_estimativa_da_api_fica_gravada(self):
        Municipio.objects.filter(pk__in=[self.curitiba.pk, self.sao_paulo.pk]).update(
            latitude="-25.4290000", longitude="-49.2671000"
        )
        self.curitiba.refresh_from_db()
        self.sao_paulo.refresh_from_db()
        resposta_api = {"features": [{"properties": {"summary": {"distance": 410200, "duration": 19800}}}]}
        chave = f"viagens:estimativa:{self.curitiba.pk}:{self.sao_paulo.pk}"
        cache.delete(chave)
        with mock.patch.object(rota, "_chamar_ors", return_value=resposta_api) as chamada:
            rota.estimar_trecho(self.curitiba, self.sao_paulo)
            registro = DistanciaMunicipios.objects.get(origem=self.curitiba, destino=self.sao_paulo)
            self.assertEqual(registro.distancia_km, Decimal("410.20"))
            # Segunda consulta, sem o cache de memória: sai da tabela, sem nova chamada.
            cache.delete(chave)
            rota.estimar_trecho(self.curitiba, self.sao_paulo)
        self.assertEqual(chamada.call_count, 1)

    def test_correcao_manual_nao_e_sobrescrita_por_estimativa(self):
        distancias.corrigir(self.curitiba.pk, self.sao_paulo.pk, "400")
        distancias.registrar(self.curitiba.pk, self.sao_paulo.pk, 999, fonte=DistanciaMunicipios.Fonte.SERVICO)
        registro = distancias.buscar(self.curitiba.pk, self.sao_paulo.pk)
        self.assertEqual(registro.distancia_km, Decimal("400.00"))
        self.assertEqual(registro.fonte, DistanciaMunicipios.Fonte.MANUAL)
        with self.assertRaises(ValueError):
            distancias.corrigir(self.curitiba.pk, self.sao_paulo.pk, "0")

    def test_carga_a_partir_dos_trechos_existentes(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        roteiro.trechos.update(distancia_km=Decimal("410.00"))
        self.assertEqual(distancias.carregar_dos_roteiros(), 3)
        self.assertEqual(distancias.carregar_dos_roteiros(), 0)
        trecho = roteiro.trechos.order_by("ordem").first()
        self.assertEqual(distancias.distancia_do_trecho(trecho), Decimal("410.00"))

    def test_trecho_sem_par_guardado_passa_a_ficar_guardado(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        trecho = roteiro.trechos.order_by("ordem").first()
        self.assertIsNone(distancias.distancia_do_trecho(trecho))
        trecho.distancia_km = Decimal("412.30")
        trecho.save()
        self.assertEqual(distancias.distancia_do_trecho(trecho), Decimal("412.30"))
        self.assertTrue(
            DistanciaMunicipios.objects.filter(
                origem=self.curitiba, destino=self.sao_paulo, fonte=DistanciaMunicipios.Fonte.ROTEIRO
            ).exists()
        )
