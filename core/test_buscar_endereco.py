"""Buscador de endereço (core.buscar_endereco): fontes, cache, limite e telas."""

import io
import json
import socket
from datetime import date
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import unquote

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Estado, Municipio, OrgaoResponsavel, Regiao, TipoEvento
from core import buscar_endereco as be
from demandas_eventos.models import DemandaEvento
from solicitacoes.models import SolicitacaoEvento

URL = reverse("core:buscar_endereco")


class _Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _json(dados):
    return _Resposta(json.dumps(dados).encode("utf-8"))


VIACEP_XV = [
    {"cep": "84010-000", "logradouro": "Rua XV de Novembro", "bairro": "Centro", "localidade": "Ponta Grossa", "uf": "PR"},
    {"cep": "84010-020", "logradouro": "Rua XV de Novembro", "bairro": "Uvaranas", "localidade": "Ponta Grossa", "uf": "PR"},
]
NOMINATIM_UVARANAS = [
    {
        "name": "Uvaranas", "addresstype": "suburb",
        "address": {"suburb": "Uvaranas", "city": "Ponta Grossa", "ISO3166-2-lvl4": "BR-PR", "postcode": "84031-000"},
    },
    {
        "name": "Ginásio Municipal", "addresstype": "leisure",
        "address": {"road": "Avenida Visconde de Taunay", "suburb": "Ronda", "city": "Ponta Grossa", "ISO3166-2-lvl4": "BR-PR"},
    },
    {"name": "Ponta Grossa", "addresstype": "city", "address": {"city": "Ponta Grossa", "ISO3166-2-lvl4": "BR-PR"}},
]


class Externos:
    """Troca o urlopen do ViaCEP e do Nominatim e anota as URLs pedidas."""

    def __init__(self, viacep=None, nominatim=None):
        self.viacep = viacep
        self.nominatim = nominatim
        self.urls = []

    def _responder(self, resposta):
        if isinstance(resposta, BaseException):
            raise resposta
        return _json(resposta)

    def viacep_urlopen(self, pedido, timeout=None):
        self.urls.append(pedido.full_url)
        assert timeout is not None and timeout <= 4
        return self._responder(self.viacep)

    def nominatim_urlopen(self, pedido, timeout=None):
        self.urls.append(pedido.full_url)
        assert timeout is not None and timeout <= 4
        assert pedido.get_header("User-agent")
        return self._responder(self.nominatim)

    def __enter__(self):
        self._patches = [
            patch("viagens_cadastros.cep.urlopen", side_effect=self.viacep_urlopen),
            patch("viagens_cadastros.geocodificacao.urllib.request.urlopen", side_effect=self.nominatim_urlopen),
            patch("core.buscar_endereco.time.sleep"),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *args):
        for p in self._patches:
            p.stop()


class BaseBuscarEndereco(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pr = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        regiao = Regiao.objects.get_or_create(nome="Região Endereço")[0]
        cls.pg = Municipio.objects.get_or_create(nome="Ponta Grossa", estado=cls.pr, defaults={"regiao": regiao})[0]
        cls.curitiba = Municipio.objects.get_or_create(nome="Curitiba", estado=cls.pr, defaults={"regiao": regiao})[0]
        cls.sjp = Municipio.objects.get_or_create(nome="São José dos Pinhais", estado=cls.pr, defaults={"regiao": regiao})[0]
        cls.user = get_user_model().objects.create_superuser("root_endereco", password="x")
        cls.tipo = TipoEvento.objects.create(nome="Ação endereço")
        cls.orgao = OrgaoResponsavel.objects.create(nome="Órgão endereço")

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)

    def get(self, **parametros):
        resposta = self.client.get(URL, parametros)
        self.assertEqual(resposta.status_code, 200)
        return resposta.json()


class PermissaoTests(BaseBuscarEndereco):
    def test_anonimo_nao_acessa(self):
        self.client.logout()
        with Externos(viacep=VIACEP_XV) as ext:
            resposta = self.client.get(URL, {"q": "Rua XV", "municipio": self.pg.pk})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(ext.urls, [])

    def test_so_get(self):
        self.assertEqual(self.client.post(URL, {"q": "Rua XV"}).status_code, 405)

    def test_menos_de_tres_letras_nao_busca(self):
        with Externos(viacep=VIACEP_XV) as ext:
            dados = self.get(q="ru", municipio=self.pg.pk)
        self.assertEqual(dados, {"resultados": [], "avisos": []})
        self.assertEqual(ext.urls, [])


class ViaCEPTests(BaseBuscarEndereco):
    def test_rua_na_cidade_da_tela(self):
        with Externos(viacep=VIACEP_XV) as ext:
            dados = self.get(q="Rua XV de Novembro", municipio=self.pg.pk)
        self.assertEqual(len(ext.urls), 1)
        self.assertEqual(unquote(ext.urls[0]), "https://viacep.com.br/ws/PR/Ponta Grossa/Rua XV de Novembro/json/")
        primeiro = dados["resultados"][0]
        self.assertEqual(primeiro["fonte"], "cep")
        self.assertEqual(primeiro["logradouro"], "Rua XV de Novembro")
        self.assertEqual(primeiro["bairro"], "Centro")
        self.assertEqual(primeiro["cep"], "84010-000")
        self.assertEqual(primeiro["municipio_id"], self.pg.pk)
        self.assertEqual(primeiro["estado_id"], self.pr.pk)
        self.assertEqual(primeiro["uf"], "PR")
        self.assertEqual(dados["avisos"], [])

    def test_numero_da_busca_fica_e_nao_vai_para_fora(self):
        with Externos(viacep=VIACEP_XV) as ext:
            dados = self.get(q="Rua XV de Novembro, 500", municipio=self.pg.pk)
        self.assertNotIn("500", unquote(ext.urls[0]))
        self.assertEqual(dados["resultados"][0]["numero"], "500")
        self.assertEqual(dados["resultados"][0]["rotulo"], "Rua XV de Novembro, 500")

    def test_cep_digitado(self):
        resposta = {"cep": "84010-000", "logradouro": "Rua XV de Novembro", "bairro": "Centro", "localidade": "Ponta Grossa", "uf": "PR"}
        with Externos(viacep=resposta) as ext:
            dados = self.get(q="84010-000")
        self.assertEqual(ext.urls, ["https://viacep.com.br/ws/84010000/json/"])
        self.assertEqual(dados["resultados"][0]["municipio_id"], self.pg.pk)
        self.assertEqual(dados["resultados"][0]["fonte"], "cep")

    def test_viacep_fora_usa_o_mapa(self):
        with Externos(viacep=URLError("fora"), nominatim=NOMINATIM_UVARANAS) as ext:
            dados = self.get(q="Uvaranas", municipio=self.pg.pk)
        self.assertEqual(len(ext.urls), 2)
        self.assertTrue(dados["resultados"])
        self.assertEqual(dados["avisos"], [])

    def test_timeout_dos_dois_so_cadastro_e_aviso(self):
        SolicitacaoEvento.objects.create(
            data_inicio_evento=date(2026, 10, 1), municipio=self.pg, tipo_evento=self.tipo, orgao_responsavel=self.orgao,
            criado_por=self.user, local_evento="Colégio Estadual", endereco="Rua XV de Novembro, 10", bairro="Centro", cep="84010-000",
        )
        with Externos(viacep=socket.timeout("lento"), nominatim=socket.timeout("lento")):
            dados = self.get(q="Rua XV", municipio=self.pg.pk)
        self.assertEqual([r["fonte"] for r in dados["resultados"]], ["cadastro"])
        self.assertEqual(dados["avisos"], [be.AVISO_FORA])
        self.assertIn("Sem resposta do serviço de CEP/mapa", dados["avisos"][0])


class NominatimTests(BaseBuscarEndereco):
    def test_bairro_e_lugar_pelo_mapa(self):
        with Externos(viacep=[], nominatim=NOMINATIM_UVARANAS) as ext:
            dados = self.get(q="Uvaranas", municipio=self.pg.pk)
        mapa = unquote(ext.urls[1].replace("+", " "))
        self.assertIn("q=Uvaranas, Ponta Grossa, PR, Brasil", mapa)
        self.assertIn("countrycodes=br", mapa)
        self.assertIn("addressdetails=1", mapa)
        bairro, lugar = dados["resultados"]  # a cidade inteira não vira sugestão
        self.assertEqual((bairro["fonte"], bairro["bairro"], bairro["logradouro"], bairro["cep"]), ("mapa", "Uvaranas", "", "84031-000"))
        self.assertEqual(bairro["municipio_id"], self.pg.pk)
        self.assertEqual(lugar["local"], "Ginásio Municipal")
        self.assertEqual(lugar["logradouro"], "Avenida Visconde de Taunay")
        self.assertEqual(lugar["bairro"], "Ronda")
        self.assertTrue(lugar["rotulo"].startswith("Ginásio Municipal — "))

    def test_mapa_vazio(self):
        with Externos(viacep=[], nominatim=[]):
            dados = self.get(q="Lugar Que Não Existe", municipio=self.pg.pk)
        self.assertEqual(dados, {"resultados": [], "avisos": []})

    def test_sem_municipio_nao_chama_viacep_por_rua(self):
        with Externos(viacep=VIACEP_XV, nominatim=[]) as ext:
            self.get(q="Rua XV de Novembro", uf=self.pr.pk)
        self.assertEqual(len(ext.urls), 1)
        self.assertIn("nominatim", ext.urls[0])
        self.assertIn("PR", unquote(ext.urls[0]))


class CadastroTests(BaseBuscarEndereco):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        comum = dict(tipo_evento=cls.tipo, orgao_responsavel=cls.orgao, criado_por=cls.user, data_inicio_evento=date(2026, 10, 1))
        SolicitacaoEvento.objects.create(
            municipio=cls.pg, local_evento="Ginásio Municipal", endereco="Avenida Visconde de Taunay, 950",
            bairro="Ronda", cep="84051000", **comum,
        )
        SolicitacaoEvento.objects.create(
            municipio=cls.curitiba, local_evento="Ginásio do Tarumã", endereco="Rua Konrad Adenauer, 370",
            bairro="Tarumã", cep="82821-020", **comum,
        )
        DemandaEvento.objects.create(
            data_solicitacao=date(2026, 9, 1), solicitante="Escola", municipio=cls.pg, local="Colégio Uvaranas",
            endereco="Rua Carlos Cavalcanti, 4748", bairro="Uvaranas", cep="84030-000",
        )

    def test_nome_do_local_sem_acento_e_filtrado_pelo_municipio(self):
        with Externos(viacep=[], nominatim=[]):
            dados = self.get(q="ginasio", municipio=self.pg.pk)
        locais = [r for r in dados["resultados"] if r["fonte"] == "cadastro"]
        self.assertEqual(len(locais), 1)
        item = locais[0]
        self.assertEqual(item["local"], "Ginásio Municipal")
        self.assertEqual(item["logradouro"], "Avenida Visconde de Taunay")
        self.assertEqual(item["numero"], "950")
        self.assertEqual(item["cep"], "84051-000")
        self.assertEqual(item["municipio_id"], self.pg.pk)

    def test_bairro_da_palestra(self):
        with Externos(viacep=[], nominatim=[]):
            dados = self.get(q="Uvaranas", municipio=self.pg.pk)
        self.assertEqual(dados["resultados"][0]["local"], "Colégio Uvaranas")

    def test_sem_municipio_procura_em_todos(self):
        with Externos(viacep=[], nominatim=[]):
            dados = self.get(q="Ginásio")
        self.assertEqual({r["municipio_nome"] for r in dados["resultados"]}, {"Ponta Grossa", "Curitiba"})

    def test_cadastro_vem_antes_e_sem_repetir(self):
        viacep = [{"cep": "84051-000", "logradouro": "Avenida Visconde de Taunay", "bairro": "Ronda", "localidade": "Ponta Grossa", "uf": "PR"},
                  {"cep": "84051-001", "logradouro": "Avenida Visconde de Taunay", "bairro": "Oficinas", "localidade": "Ponta Grossa", "uf": "PR"}]
        with Externos(viacep=viacep, nominatim=[]):
            dados = self.get(q="Visconde de Taunay", municipio=self.pg.pk)
        self.assertEqual([(r["fonte"], r["bairro"]) for r in dados["resultados"]], [("cadastro", "Ronda"), ("cep", "Oficinas")])


class MunicipioTests(BaseBuscarEndereco):
    def test_nome_sem_acento_e_uf(self):
        self.assertEqual(be.municipio_do_cadastro("SAO JOSE DOS PINHAIS", "pr")[0], self.sjp.pk)
        self.assertEqual(be.municipio_do_cadastro("São José dos Pinhais", "PR")[2], self.pr.pk)
        self.assertIsNone(be.municipio_do_cadastro("São José dos Pinhais", "SC"))
        self.assertIsNone(be.municipio_do_cadastro("Cidade Inventada", "PR"))

    def test_cidade_fora_do_cadastro_fica_so_com_o_nome(self):
        viacep = [{"cep": "88000-000", "logradouro": "Rua Tal", "bairro": "Centro", "localidade": "Cidade Inventada", "uf": "PR"}]
        with Externos(viacep=viacep):
            dados = self.get(q="Rua Tal", municipio=self.pg.pk)
        self.assertIsNone(dados["resultados"][0]["municipio_id"])
        self.assertEqual(dados["resultados"][0]["municipio_nome"], "Cidade Inventada")

    def test_separar_numero(self):
        self.assertEqual(be.separar_numero("Rua XV de Novembro 500"), ("Rua XV de Novembro", "500"))
        self.assertEqual(be.separar_numero("Rua 7 de Setembro"), ("Rua 7 de Setembro", ""))
        self.assertEqual(be.separar_numero("Rodovia BR 376"), ("Rodovia BR 376", ""))
        self.assertEqual(be.separar_numero_gravado("Rua das Flores, 123, sala 2"), ("Rua das Flores", "123, sala 2"))


class CacheELimiteTests(BaseBuscarEndereco):
    def test_mesma_consulta_normalizada_usa_o_cache(self):
        with Externos(viacep=VIACEP_XV) as ext:
            primeira = self.get(q="Rua XV de Novembro", municipio=self.pg.pk)
            segunda = self.get(q="  rua xv DE novembro ", municipio=self.pg.pk)
        self.assertEqual(len(ext.urls), 1)
        self.assertEqual(primeira, segunda)

    def test_erro_nao_fica_no_cache(self):
        with Externos(viacep=URLError("fora"), nominatim=URLError("fora")):
            self.get(q="Rua XV de Novembro", municipio=self.pg.pk)
        with Externos(viacep=VIACEP_XV) as ext:
            dados = self.get(q="Rua XV de Novembro", municipio=self.pg.pk)
        self.assertEqual(len(ext.urls), 1)
        self.assertTrue(dados["resultados"])

    def test_limite_por_usuario(self):
        with patch.object(be, "LIMITE_POR_USUARIO", 2), Externos(viacep=VIACEP_XV) as ext:
            self.get(q="Rua Um", municipio=self.pg.pk)
            self.get(q="Rua Dois", municipio=self.pg.pk)
            dados = self.get(q="Rua Três", municipio=self.pg.pk)
        self.assertEqual(len(ext.urls), 2)
        self.assertEqual(dados["avisos"], [be.AVISO_LIMITE])


class ComponenteNasTelasTests(BaseBuscarEndereco):
    def test_buscador_nas_tres_telas(self):
        for nome in ("solicitacoes:nova", "coffee_break:nova", "demandas_eventos:nova"):
            with self.subTest(tela=nome):
                resposta = self.client.get(reverse(nome))
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "data-buscar-endereco")
                self.assertContains(resposta, f'data-url="{URL}"')
                self.assertContains(resposta, 'role="combobox"')
                self.assertContains(resposta, "js/buscar-endereco.js")
                self.assertContains(resposta, 'name="endereco"')
