import json
from unittest.mock import patch
from urllib.error import URLError

from django.urls import reverse

from cadastros.models import Estado
from .cep import consultar_cep
from .models import ConfiguracaoSistema
from .tests import BaseViagensTestCase


class ConsultaCEPTests(BaseViagensTestCase):
    def setUp(self):
        self.client.force_login(self.criar_usuario("consulta_cep"))
        self.url = reverse("viagens_cadastros:api_consulta_cep", args=["01001000"])

    @patch("viagens_cadastros.cep.urlopen")
    def test_consulta_retorna_endereco_e_nao_cria_configuracao(self, abrir):
        Estado.objects.update_or_create(sigla="SP", defaults={"nome": "SÃO PAULO", "codigo_ibge": 35})
        abrir.return_value.__enter__.return_value.read.return_value = json.dumps({"cep": "01001-000", "logradouro": "Praça da Sé", "bairro": "Sé", "localidade": "São Paulo", "uf": "sp", "estado": "Nome externo"}).encode()
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"cep": "01001-000", "logradouro": "Praça da Sé", "bairro": "Sé", "cidade": "São Paulo", "uf": "SP", "estado": "SÃO PAULO"})
        chamada = abrir.call_args
        self.assertEqual(chamada.args[0].full_url, "https://viacep.com.br/ws/01001000/json/")
        self.assertEqual(chamada.kwargs["timeout"], 5)
        self.assertFalse(ConfiguracaoSistema.objects.exists())

    @patch("viagens_cadastros.cep.urlopen")
    def test_formato_invalido_nao_consulta_servico(self, abrir):
        resposta = self.client.get(reverse("viagens_cadastros:api_consulta_cep", args=["123"]))
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"erro": "CEP deve ter 8 dígitos."})
        abrir.assert_not_called()

    @patch("viagens_cadastros.cep.urlopen")
    def test_nao_encontrado_e_indisponibilidade_tem_respostas_distintas(self, abrir):
        abrir.return_value.__enter__.return_value.read.return_value = b'{"erro":true}'
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 404)
        self.assertEqual(resposta.json(), {"erro": "CEP não encontrado."})
        abrir.side_effect = URLError("indisponível")
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 502)
        self.assertEqual(resposta.json(), {"erro": "Erro ao consultar serviço externo de CEP."})

    @patch("viagens_cadastros.cep.urlopen")
    def test_resposta_invalida_e_timeout_nao_viram_erro_500(self, abrir):
        for conteudo in [b'not-json', b'[]']:
            abrir.return_value.__enter__.return_value.read.return_value = conteudo
            self.assertEqual(self.client.get(self.url).status_code, 502)
        abrir.side_effect = TimeoutError()
        self.assertEqual(self.client.get(self.url).status_code, 502)

    @patch("viagens_cadastros.cep.urlopen")
    def test_fallback_de_cep_e_estado_sem_escrever_cadastro(self, abrir):
        abrir.return_value.__enter__.return_value.read.return_value = b'{"uf":"ZZ","estado":"Nome externo"}'
        self.assertEqual(consultar_cep("01001000"), {"cep": "01001-000", "logradouro": "", "bairro": "", "cidade": "", "uf": "ZZ", "estado": "Nome externo"})
        self.assertFalse(Estado.objects.filter(sigla="ZZ").exists())

    @patch("viagens_cadastros.cep.urlopen")
    def test_exige_modulo_e_nao_aceita_post(self, abrir):
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        usuario = self.criar_usuario("cep_sem_modulo")
        usuario.setores.clear()
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        abrir.assert_not_called()
