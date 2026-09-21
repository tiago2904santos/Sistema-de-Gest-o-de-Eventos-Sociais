"""A integração por dentro: configuração, transporte e mascaramento.

Nenhum teste aqui toca a rede — o ``urlopen`` é substituído por um dublê. O
que se protege é o contrato que o resto do sistema assume: sem credencial
nada sai, status de erro vira exceção própria e segredo nenhum chega ao log.
"""

import io
import json
import urllib.error
from unittest import mock

from django.test import SimpleTestCase, override_settings

from . import settings as cfg
from .client import EProtocoloClient, mascarar_dados
from .exceptions import (
    EProtocoloAuthError,
    EProtocoloNaoConfiguradoError,
    EProtocoloTimeoutError,
    EProtocoloUnavailableError,
)
from .mocks import gerar_numero_mock

CONFIG_REAL = {
    "AMBIENTE": "homologacao",
    "BASE_URL": "https://exemplo.invalido/spi-servicos",
    "TOKEN_URL": "https://exemplo.invalido/token",
    "CLIENT_ID": "cliente",
    "CLIENT_SECRET": "segredo",
    "CONSUMER_ID": "consumidor",
    "TIMEOUT": 5,
    "VERIFY_SSL": True,
    "REAL_READONLY": False,
}


class _Resposta(io.BytesIO):
    """O mínimo que o ``urlopen`` devolve e o client lê."""

    def __init__(self, corpo: bytes, status: int = 200):
        super().__init__(corpo)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


def _respostas(*corpos):
    """Dublê do ``urlopen``: uma resposta por chamada, na ordem."""
    return mock.Mock(side_effect=list(corpos))


class ConfiguracaoTests(SimpleTestCase):
    @override_settings(EPROTOCOLO={"AMBIENTE": "mock"})
    def test_sem_credencial_o_modo_e_simulado(self):
        self.assertTrue(cfg.em_modo_mock())
        self.assertFalse(cfg.eprotocolo_esta_configurado())
        self.assertFalse(cfg.mutacao_real_liberada())

    @override_settings(EPROTOCOLO={**CONFIG_REAL, "CLIENT_SECRET": ""})
    def test_ambiente_real_sem_credencial_completa_cai_para_simulado(self):
        self.assertTrue(cfg.em_modo_mock())
        self.assertIn("CLIENT_SECRET", cfg.campos_faltantes())
        self.assertIn("credenciais do eProtocolo ausentes", cfg.descricao_ambiente())
        self.assertFalse(cfg.validar_configuracao()["ok"])

    @override_settings(EPROTOCOLO=CONFIG_REAL)
    def test_credencial_completa_com_trava_aberta_libera_a_gravacao(self):
        self.assertFalse(cfg.em_modo_mock())
        self.assertTrue(cfg.mutacao_real_liberada())
        self.assertEqual(cfg.descricao_ambiente(), "Integração ativa (homologacao)")

    @override_settings(EPROTOCOLO={**CONFIG_REAL, "REAL_READONLY": True})
    def test_trava_fechada_mantem_a_integracao_em_somente_consulta(self):
        self.assertFalse(cfg.mutacao_real_liberada())
        self.assertIn("somente consulta", cfg.descricao_ambiente())

    def test_diagnostico_nunca_devolve_o_segredo(self):
        with override_settings(EPROTOCOLO=CONFIG_REAL):
            info = cfg.validar_configuracao()
        self.assertNotIn("segredo", json_dumps(info))
        self.assertEqual(info["client_id"], "clie***")
        self.assertTrue(info["client_secret_configurado"])


def json_dumps(valor) -> str:
    return json.dumps(valor, ensure_ascii=False)


class MascaramentoTests(SimpleTestCase):
    def test_token_secret_e_cpf_nao_chegam_ao_log(self):
        limpo = mascarar_dados({
            "Authorization": "Bearer abc",
            "client_secret": "segredo",
            "cpfInteressado": "11122233344",
            "servidores": [{"cpf": "55566677788", "nome": "ANA"}],
            "assunto": "Diárias",
        })
        self.assertEqual(limpo["Authorization"], "***")
        self.assertEqual(limpo["client_secret"], "***")
        self.assertEqual(limpo["cpfInteressado"], "111.***.***-44")
        self.assertEqual(limpo["servidores"][0]["cpf"], "555.***.***-88")
        self.assertEqual(limpo["servidores"][0]["nome"], "ANA")
        self.assertEqual(limpo["assunto"], "Diárias")

    def test_cpf_incompleto_vira_asteriscos(self):
        self.assertEqual(mascarar_dados({"cpf": "123"})["cpf"], "***")


class ClientTests(SimpleTestCase):
    def _client(self, **extra):
        return EProtocoloClient(config={**CONFIG_REAL, **extra})

    def test_token_e_reaproveitado_entre_chamadas(self):
        token = _Resposta(json.dumps({"access_token": "t", "expires_in": 300}).encode())
        primeira = _Resposta(b'{"numero": "1"}')
        segunda = _Resposta(b'{"numero": "2"}')
        with mock.patch("urllib.request.urlopen", _respostas(token, primeira, segunda)) as urlopen:
            client = self._client()
            client.get("/v3/protocolos/1")
            client.get("/v3/protocolos/2")
        # Três chamadas: um token e duas consultas — o token não foi pedido de novo.
        self.assertEqual(urlopen.call_count, 3)

    def test_cabecalhos_obrigatorios_vao_na_requisicao(self):
        token = _Resposta(json.dumps({"access_token": "t", "expires_in": 300}).encode())
        with mock.patch("urllib.request.urlopen", _respostas(token, _Resposta(b"{}"))) as urlopen:
            self._client().post("/v3/protocolos", json_body={"assunto": "x"})
        pedido = urlopen.call_args_list[-1].args[0]
        self.assertEqual(pedido.get_header("Authorization"), "Bearer t")
        self.assertEqual(pedido.get_header("Consumerid"), "consumidor")
        self.assertEqual(pedido.method, "POST")
        self.assertEqual(json.loads(pedido.data)["assunto"], "x")

    def test_url_monta_a_partir_da_base(self):
        token = _Resposta(json.dumps({"access_token": "t", "expires_in": 300}).encode())
        with mock.patch("urllib.request.urlopen", _respostas(token, _Resposta(b"{}"))) as urlopen:
            self._client().get("/v3/locais", params={"codOrgao": "10"})
        url = urlopen.call_args_list[-1].args[0].full_url
        self.assertEqual(url, "https://exemplo.invalido/spi-servicos/v3/locais?codOrgao=10")

    def test_401_vira_erro_de_autenticacao(self):
        token = _Resposta(json.dumps({"access_token": "t", "expires_in": 300}).encode())
        erro = urllib.error.HTTPError("u", 401, "nao autorizado", {}, io.BytesIO(b"{}"))
        with mock.patch("urllib.request.urlopen", _respostas(token, erro)):
            with self.assertRaises(EProtocoloAuthError):
                self._client().get("/v3/protocolos/1")

    def test_5xx_vira_indisponibilidade(self):
        token = _Resposta(json.dumps({"access_token": "t", "expires_in": 300}).encode())
        erro = urllib.error.HTTPError("u", 503, "fora do ar", {}, io.BytesIO(b"{}"))
        with mock.patch("urllib.request.urlopen", _respostas(token, erro)):
            with self.assertRaises(EProtocoloUnavailableError):
                self._client().get("/v3/protocolos/1")

    def test_timeout_tem_excecao_propria(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
            with self.assertRaises(EProtocoloTimeoutError):
                self._client().garantir_token()

    def test_rede_fora_vira_indisponibilidade(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("sem rota")):
            with self.assertRaises(EProtocoloUnavailableError):
                self._client().garantir_token()

    def test_sem_configuracao_o_client_se_recusa_a_sair(self):
        with self.assertRaises(EProtocoloNaoConfiguradoError):
            EProtocoloClient(config={}).garantir_token()

    def test_corpo_que_nao_e_json_nao_derruba_a_chamada(self):
        token = _Resposta(json.dumps({"access_token": "t", "expires_in": 300}).encode())
        with mock.patch("urllib.request.urlopen", _respostas(token, _Resposta(b"<html>ops</html>"))):
            dados = self._client().get("/v3/protocolos/1")
        self.assertIn("ops", dados["_raw"])


class NumeroSimuladoTests(SimpleTestCase):
    def test_formato_do_numero_simulado(self):
        numero = gerar_numero_mock("semente")
        self.assertRegex(numero, r"^\d{2}\.\d{3}\.\d{3}-\d$")

    def test_mesma_semente_mesmo_numero(self):
        self.assertEqual(gerar_numero_mock(7), gerar_numero_mock(7))
        self.assertNotEqual(gerar_numero_mock(7), gerar_numero_mock(8))
