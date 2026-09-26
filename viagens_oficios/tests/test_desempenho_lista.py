"""m101: a lista de ofícios faz o mesmo número de consultas seja qual for o tamanho da página.

Quando o editor grava os horários só nos trechos (roteiro sem `saida_dt`), cada
linha voltava ao banco para o período (duas consultas por chamada, duas
chamadas por linha) e para a primeira saída (mais duas): 40 consultas com 2
ofícios, 96 com 16. Medida com poucos e com muitos, a página tem de custar o
mesmo — e o número fica travado aqui.
"""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from viagens_roteiros.models import Roteiro

from .fixtures import CenarioOficioMixin

#: Consultas da página da lista, com roteiros que só têm horários nos trechos.
CONSULTAS_DA_LISTA = 41


class ListaOficiosConsultasTests(CenarioOficioMixin, TestCase):
    def _consultas_da_lista(self):
        with CaptureQueriesContext(connection) as contexto:
            response = self.client.get(reverse("viagens_oficios:lista"))
        self.assertEqual(response.status_code, 200)
        return len(contexto), response

    def test_numero_de_consultas_nao_cresce_com_a_pagina(self):
        for _ in range(2):
            self.criar()
        # Como o editor F2 grava: período só nos trechos.
        Roteiro.objects.update(saida_dt=None, retorno_chegada_dt=None)
        poucos, response = self._consultas_da_lista()
        linha = response.context["linhas"][0]
        self.assertIn("LONDRINA/PR · 10/09/2026", linha["titulo"])
        self.assertEqual(linha["tipo"]["rotulo"], "Autorização")

        for _ in range(6):
            self.criar()
        Roteiro.objects.update(saida_dt=None, retorno_chegada_dt=None)
        muitos, response = self._consultas_da_lista()
        self.assertEqual(len(response.context["linhas"]), 8)
        self.assertEqual(muitos, poucos, "a lista voltou a consultar o banco por ofício")
        with self.assertNumQueries(CONSULTAS_DA_LISTA):
            self.client.get(reverse("viagens_oficios:lista"))
