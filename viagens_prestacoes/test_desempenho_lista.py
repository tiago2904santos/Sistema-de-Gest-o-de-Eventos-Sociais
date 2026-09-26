"""m101: a lista de prestações faz o mesmo número de consultas seja qual for o tamanho da página.

Antes, cada cartão voltava ao banco para o período do roteiro (duas consultas
por chamada, três chamadas por cartão), os destinos, os anexos compartilhados e
o título do ofício: 75 consultas com 2 ofícios, 291 com 16. Aqui a página é
medida com poucos e com muitos ofícios, e o número tem de ser o mesmo.
"""
from datetime import datetime, timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from cadastros.models import Estado, Municipio, Regiao
from viagens_roteiros.models import RoteiroDestino, RoteiroTrecho

from .diario_services import obter_ou_criar_diario, sincronizar_trechos
from .models import DiarioBordoTrecho, PrestacaoDocumentoAnexo
from .test_helpers import PDF_MINIMO, PrestacaoFixturesMixin, PrestacaoTestCase as TestCase

#: Consultas da página da lista, depois da primeira visita (que cria a configuração).
CONSULTAS_DA_LISTA = 33


class ListaPrestacoesConsultasTests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        self.setUpPrestacaoFixtures()
        uf = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        regiao = Regiao.objects.get_or_create(nome="Interior")[0]
        self.cidades = [
            Municipio.objects.get_or_create(codigo_ibge=4100000 + i, defaults={"nome": f"Cidade {i}", "estado": uf, "regiao": regiao})[0]
            for i in range(1, 4)
        ]
        self._proximo = 0

    def _oficio_completo(self, *, servidores=1):
        """Roteiro com horários só nos trechos (como o editor grava), três destinos e anexos."""
        from django.core.files.base import ContentFile

        self._proximo += 1
        equipe = [self.criar_servidor(f"Servidor {self._proximo}-{i}") for i in range(servidores)]
        fixture = self.criar_prestacao(numero=self._proximo, servidores=equipe, trechos_roteiro=0)
        saida = timezone.make_aware(datetime(2026, 9, 10 + self._proximo % 10, 8))
        for ordem, cidade in enumerate(self.cidades):
            RoteiroDestino.objects.create(roteiro=fixture.roteiro, municipio=cidade, ordem=ordem)
            RoteiroTrecho.objects.create(
                roteiro=fixture.roteiro, sentido=RoteiroTrecho.Sentido.IDA, ordem=ordem,
                origem_municipio=self.cidades[ordem - 1], destino_municipio=cidade,
                saida_dt=saida + timedelta(hours=ordem * 3), chegada_dt=saida + timedelta(hours=ordem * 3 + 2),
            )
        PrestacaoDocumentoAnexo.objects.create(
            prestacao=fixture.prestacao, tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO,
            arquivo=ContentFile(PDF_MINIMO, name="despacho.pdf"), nome_original="despacho.pdf",
        )
        for ps in fixture.prestacoes_servidor:
            PrestacaoDocumentoAnexo.objects.create(
                prestacao=fixture.prestacao, servidor_prestacao=ps, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE,
                arquivo=ContentFile(PDF_MINIMO, name="comprovante.pdf"), nome_original="comprovante.pdf",
            )
        return fixture

    def _consultas_da_lista(self):
        with CaptureQueriesContext(connection) as contexto:
            response = self.get_listagem()
        self.assertEqual(response.status_code, 200)
        return len(contexto), response

    def test_numero_de_consultas_nao_cresce_com_a_pagina(self):
        self._oficio_completo()
        self._oficio_completo(servidores=2)
        self.get_listagem()  # A primeira visita cria a configuração do sistema.
        poucos, response = self._consultas_da_lista()
        self.assertEqual(len(response.context["cards"]), 3)
        # O cartão continua com destino e período, agora sem voltar ao banco.
        card = response.context["cards"][0]
        self.assertIn("CIDADE 1/PR, CIDADE 2/PR +1", card["titulo"])
        self.assertTrue(card["oficio"]["periodo"])
        self.assertEqual(card["oficio"]["periodo"], card["data_evento_display"])
        self.assertTrue(card["servidores"][0]["comprovante_ok"])
        self.assertTrue(card["despacho_assinado"]["assinado"])

        for _ in range(8):
            self._oficio_completo(servidores=2)
        muitos, response = self._consultas_da_lista()
        self.assertEqual(len(response.context["cards"]), 19)
        self.assertEqual(muitos, poucos, "a lista voltou a consultar o banco por cartão")
        with self.assertNumQueries(CONSULTAS_DA_LISTA):
            self.get_listagem()


class SincronizarTrechosSemMudancaTests(PrestacaoFixturesMixin, TestCase):
    """m101: com o diário já espelhando o roteiro, a sincronização não grava nada."""

    def setUp(self):
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1, trechos_roteiro=3)
        self.diario = obter_ou_criar_diario(self.fixture.prestacao)

    def test_segunda_chamada_so_le(self):
        linhas = sincronizar_trechos(self.diario)
        self.assertEqual(len(linhas), 3)
        linhas[1].km_inicial = 100
        linhas[1].save()
        with CaptureQueriesContext(connection) as contexto:
            de_novo = sincronizar_trechos(self.diario)
        self.assertEqual([l.pk for l in de_novo], [l.pk for l in linhas])
        self.assertEqual(de_novo[1].km_inicial, 100)
        gravacoes = [q["sql"] for q in contexto.captured_queries if q["sql"].startswith(("UPDATE", "INSERT", "DELETE"))]
        self.assertEqual(gravacoes, [])

    def test_roteiro_alterado_ainda_sincroniza(self):
        sincronizar_trechos(self.diario)
        RoteiroTrecho.objects.create(roteiro=self.fixture.roteiro, sentido=RoteiroTrecho.Sentido.IDA, ordem=3)
        self.assertEqual(len(sincronizar_trechos(self.diario)), 4)
        self.fixture.roteiro.trechos.filter(ordem=0).delete()
        self.assertEqual([l.ordem for l in sincronizar_trechos(self.diario)], [0, 1, 2])
        self.assertEqual(DiarioBordoTrecho.objects.filter(diario=self.diario).count(), 3)
