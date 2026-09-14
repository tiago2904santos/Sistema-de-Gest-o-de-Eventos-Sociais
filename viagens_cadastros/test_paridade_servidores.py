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

    def test_formulario_invalido_preserva_valor_no_modal(self):
        url = reverse("viagens_cadastros:novo", args=["servidores"])
        resposta = self.client.post(url, {"nome": "MARIA", "cpf": "11111111111"}, HTTP_X_CADASTRO_MODAL="1")
        self.assertTemplateUsed(resposta, "pages/viagens_cadastros/_modal_form.html")
        self.assertContains(resposta, "CPF inválido")
        self.assertContains(resposta, 'value="MARIA"')
        self.assertFalse(Servidor.objects.filter(nome="MARIA").exists())

    def test_documento_repetido_avisa_em_vez_de_mostrar_a_constraint(self):
        Servidor.objects.create(nome="JA CADASTRADO", cpf="52998224725", rg="123456789")
        novo = reverse("viagens_cadastros:novo", args=["servidores"])
        resposta = self.client.post(
            novo, {"nome": "OUTRA PESSOA", "cpf": "529.982.247-25"}, HTTP_X_CADASTRO_MODAL="1"
        )
        self.assertContains(resposta, "Já existe um servidor com este CPF.")
        self.assertNotContains(resposta, "viagens_servidor_cpf_unico")
        resposta = self.client.post(
            novo, {"nome": "OUTRA PESSOA", "rg": "12.345.678-9"}, HTTP_X_CADASTRO_MODAL="1"
        )
        self.assertContains(resposta, "Já existe um servidor com este RG.")
        self.assertFalse(Servidor.objects.filter(nome="OUTRA PESSOA").exists())

    def test_edicao_do_proprio_servidor_nao_acusa_documento_repetido(self):
        servidor = Servidor.objects.create(nome="MESMA PESSOA", cpf="52998224725", rg="123456789")
        resposta = self.client.post(
            reverse("viagens_cadastros:editar", args=["servidores", servidor.pk]),
            {"nome": "MESMA PESSOA EDITADA", "cpf": "529.982.247-25", "rg": "12.345.678-9"},
            HTTP_X_CADASTRO_MODAL="1",
        )
        self.assertEqual(resposta.json(), {"ok": True})
        servidor.refresh_from_db()
        self.assertEqual(servidor.nome, "MESMA PESSOA EDITADA")

    def test_criacao_de_cargo_respeita_retorno_interno_e_recusa_externo(self):
        url = reverse("viagens_cadastros:novo", args=["cargos"])
        retorno = reverse("viagens_cadastros:lista", args=["servidores"])
        resposta = self.client.post(url, {"nome": "CARGO NOVO", "next": retorno})
        self.assertRedirects(resposta, retorno)
        resposta = self.client.post(url, {"nome": "OUTRO CARGO", "next": "https://externo.example/"})
        self.assertRedirects(resposta, reverse("viagens_cadastros:lista", args=["cargos"]))
