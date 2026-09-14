from django.urls import reverse

from .models import Cargo, Servidor
from .permissions import GRUPO_OPERADOR
from .tests import BaseViagensTestCase


class ParidadeServidoresTests(BaseViagensTestCase):
    def setUp(self):
        self.client.force_login(self.criar_usuario("paridade", GRUPO_OPERADOR))
        self.lista = reverse("viagens_cadastros:lista", args=["servidores"])

    def test_busca_sem_acentos_por_cargo_e_unidade(self):
        Servidor.objects.create(nome="JOÃO ALMEIDA", cargo=self.cargo, unidade=self.unidade)
        Servidor.objects.create(nome="OUTRA PESSOA")
        for termo in ("joao", "investigador", "delegacia", "DC"):
            with self.subTest(termo=termo):
                resposta = self.client.get(self.lista, {"q": termo})
                self.assertContains(resposta, "JOÃO ALMEIDA")
                self.assertNotContains(resposta, "OUTRA PESSOA")

    def test_filtro_de_cargo_preserva_busca_e_contagens(self):
        outro = Cargo.objects.create(nome="PAPILOSCOPISTA")
        Servidor.objects.create(nome="MARIA UM", cargo=self.cargo)
        Servidor.objects.create(nome="MARIA DOIS", cargo=outro)
        Servidor.objects.create(nome="ANA", cargo=outro)
        resposta = self.client.get(self.lista, {"q": "maria", "cargo": self.cargo.pk})
        self.assertContains(resposta, "MARIA UM")
        self.assertNotContains(resposta, "MARIA DOIS")
        filtros = resposta.context["filtros_cargo"]
        self.assertEqual([(x["nome"], x["total"]) for x in filtros], [("Todos", 2), ("PAPILOSCOPISTA", 1), ("INVESTIGADOR", 1)])
        self.assertIn("q=maria", filtros[1]["url"])

    def test_cargo_invalido_nao_causa_erro_nem_oculta_todos(self):
        Servidor.objects.create(nome="MARIA")
        for cargo in ("xyz", "9" * 100, "999999999"):
            self.assertContains(self.client.get(self.lista, {"cargo": cargo}), "MARIA")

    def test_paginacao_de_25_preserva_filtros(self):
        for n in range(26):
            Servidor.objects.create(nome=f"PESSOA {n:02d}", cargo=self.cargo)
        resposta = self.client.get(self.lista, {"q": "pessoa", "cargo": self.cargo.pk, "page": 2})
        self.assertEqual(resposta.context["pagina"].start_index(), 26)
        self.assertContains(resposta, "PESSOA 25")
        self.assertNotContains(resposta, "PESSOA 00")
        self.assertIn("q=pessoa", resposta.context["querystring"])
        self.assertIn(f"cargo={self.cargo.pk}", resposta.context["querystring"])

    def test_cartao_exibe_rg_e_dialogo_sem_apagar_no_get(self):
        servidor = Servidor.objects.create(nome="MARIA", rg="123456789")
        resposta = self.client.get(self.lista)
        self.assertContains(resposta, servidor.rg_formatado)
        self.assertContains(resposta, "Excluir servidor?")
        self.assertContains(resposta, "Se houver vínculos com outros registros, a exclusão será bloqueada.")
        self.assertTrue(Servidor.objects.filter(pk=servidor.pk).exists())

    def test_formulario_invalido_preserva_valor_e_links_de_retorno(self):
        url = reverse("viagens_cadastros:novo", args=["servidores"])
        resposta = self.client.post(url, {"nome": "MARIA", "cpf": "11111111111"})
        self.assertTemplateUsed(resposta, "pages/viagens_cadastros/servidores/form.html")
        self.assertContains(resposta, "CPF inválido")
        self.assertContains(resposta, 'value="MARIA"')
        self.assertContains(resposta, "Gerenciar cargos")
        self.assertContains(resposta, "next=%2Fviagens%2Fcadastros%2Fservidores%2Fnovo%2F")

    def test_criacao_de_cargo_preserva_caminho_ao_formulario_sem_redirect_externo(self):
        url = reverse("viagens_cadastros:novo", args=["cargos"])
        retorno = reverse("viagens_cadastros:novo", args=["servidores"])
        lista_cargos = self.client.get(reverse("viagens_cadastros:lista", args=["cargos"]), {"next": retorno})
        self.assertContains(lista_cargos, f'next=%2Fviagens%2Fcadastros%2Fservidores%2Fnovo%2F')
        formulario = self.client.get(url, {"next": retorno})
        self.assertEqual(formulario.context["url_retorno"], retorno)
        self.assertTemplateUsed(formulario, "pages/viagens_cadastros/cargos/lista.html")
        resposta = self.client.post(url, {"nome": "CARGO NOVO", "next": retorno})
        self.assertRedirects(resposta, reverse("viagens_cadastros:lista", args=["cargos"]) + "?next=%2Fviagens%2Fcadastros%2Fservidores%2Fnovo%2F")
        resposta = self.client.post(url, {"nome": "OUTRO CARGO", "next": "https://externo.example/"})
        self.assertRedirects(resposta, reverse("viagens_cadastros:lista", args=["cargos"]))
