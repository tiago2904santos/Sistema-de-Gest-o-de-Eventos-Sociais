from django.urls import reverse

from auditoria.models import LogAuditoria

from .models import Cargo, Combustivel, Servidor
from .permissions import GRUPO_OPERADOR
from .tests import BaseViagensTestCase


class ParidadeCatalogosTests(BaseViagensTestCase):
    def setUp(self):
        self.usuario = self.criar_usuario("catalogos", GRUPO_OPERADOR)
        self.client.force_login(self.usuario)

    def test_inclusao_normaliza_e_respeita_o_retorno(self):
        for slug, model in (("cargos", Cargo), ("combustiveis", Combustivel)):
            with self.subTest(slug=slug):
                retorno = "/viagens/cadastros/servidores/"
                response = self.client.post(
                    reverse("viagens_cadastros:novo", args=[slug]),
                    {"nome": "  nome novo  ", "next": retorno},
                )
                self.assertRedirects(response, retorno)
                self.assertTrue(model.objects.filter(nome="NOME NOVO").exists())
        self.assertEqual(LogAuditoria.objects.filter(usuario=self.usuario, acao="VIAGENS_CADASTRO_CRIADO").count(), 2)

    def test_erro_de_inclusao_reabre_o_modal_com_o_valor_digitado(self):
        response = self.client.post(
            reverse("viagens_cadastros:novo", args=["cargos"]), {"nome": self.cargo.nome.lower()}
        )
        # Sem JS a lista volta com o modal aberto; com JS o fetch recebe só o formulário.
        self.assertTrue(response.context["modal"]["erros_total"])
        self.assertContains(response, "data-cadastro-inicial")
        self.assertContains(response, self.cargo.nome)
        self.assertEqual(Cargo.objects.filter(nome=self.cargo.nome).count(), 1)
        self.assertContains(response, "Já existe um cargo com este nome.")
        self.assertContains(response, "Corrija antes de continuar")

    def test_rota_novo_abre_o_modal_e_preserva_erro_de_combustivel(self):
        for slug in ["cargos", "combustiveis"]:
            url = reverse("viagens_cadastros:novo", args=[slug])
            lista = reverse("viagens_cadastros:lista", args=[slug])
            self.assertRedirects(self.client.get(url), lista + "?novo=1")
            response = self.client.get(url, HTTP_X_CADASTRO_MODAL="1")
            self.assertTemplateUsed(response, "pages/viagens_cadastros/_modal_form.html")
            # O modal traz o cadastro inteiro, inclusive a marca de padrão.
            self.assertContains(response, 'name="is_padrao"')
        Combustivel.objects.create(nome="ETANOL")
        response = self.client.post(
            reverse("viagens_cadastros:novo", args=["combustiveis"]), {"nome": "etanol"},
            HTTP_X_CADASTRO_MODAL="1",
        )
        self.assertContains(response, "Já existe um combustível com este nome.")
        self.assertContains(response, 'value="etanol"')

    def test_edicao_pelo_modal_responde_json_e_grava(self):
        url = reverse("viagens_cadastros:editar", args=["cargos", self.cargo.pk])
        response = self.client.post(url, {"nome": "cargo renomeado"}, HTTP_X_CADASTRO_MODAL="1")
        self.assertEqual(response.json(), {"ok": True})
        self.cargo.refresh_from_db()
        self.assertEqual(self.cargo.nome, "CARGO RENOMEADO")

    def test_exclusao_get_nao_grava_e_post_preserva_retorno(self):
        cargo = Cargo.objects.create(nome="EXCLUSÃO DE ENSAIO")
        url = reverse("viagens_cadastros:excluir", args=["cargos", cargo.pk])
        lista = reverse("viagens_cadastros:lista", args=["cargos"])
        self.assertRedirects(self.client.get(url), lista)
        self.assertTrue(Cargo.objects.filter(pk=cargo.pk).exists())
        response = self.client.post(url, {"next": "/viagens/"}, follow=True)
        self.assertEqual(response.redirect_chain[0][0], lista + "?next=%2Fviagens%2F")
        self.assertContains(response, "Cargo excluído com sucesso.")
        self.assertFalse(Cargo.objects.filter(pk=cargo.pk).exists())
        self.assertTrue(LogAuditoria.objects.filter(usuario=self.usuario, acao="VIAGENS_CADASTRO_EXCLUIDO").exists())

    def test_exclusao_vinculada_retorna_erro_sem_apagar(self):
        Servidor.objects.create(nome="VÍNCULO DE ENSAIO", cargo=self.cargo)
        url = reverse("viagens_cadastros:excluir", args=["cargos", self.cargo.pk])
        response = self.client.post(url, follow=True)
        self.assertContains(response, "Não foi possível excluir este cadastro porque ele está vinculado a outros registros.")
        self.assertTrue(Cargo.objects.filter(pk=self.cargo.pk).exists())
        self.assertFalse(LogAuditoria.objects.filter(usuario=self.usuario, acao="VIAGENS_CADASTRO_EXCLUIDO").exists())

    def test_busca_sem_acentos_pagina_15_e_preserva_parametros(self):
        Cargo.objects.bulk_create([Cargo(nome=f"POLÍCIA {i:02}") for i in range(17)])
        lista = reverse("viagens_cadastros:lista", args=["cargos"])
        response = self.client.get(lista, {"q": "policia", "page": 2, "next": "/viagens/"})
        self.assertEqual(response.context["pagina"].paginator.per_page, 15)
        self.assertEqual(len(response.context["itens"]), 2)
        self.assertContains(response, "POLÍCIA 16")
        self.assertNotContains(response, "POLÍCIA 00")
        self.assertIn("q=policia", response.context["querystring"])
        self.assertIn("next=%2Fviagens%2F", response.context["querystring"])

    def test_definir_padrao_troca_unico_e_get_nao_grava(self):
        for slug, model in (("cargos", Cargo), ("combustiveis", Combustivel)):
            with self.subTest(slug=slug):
                anterior = model.objects.create(nome="PADRÃO ANTERIOR", is_padrao=True)
                novo = model.objects.create(nome="NOVO PADRÃO")
                url = reverse("viagens_cadastros:definir_padrao", args=[slug, novo.pk])
                self.client.get(url)
                novo.refresh_from_db()
                self.assertFalse(novo.is_padrao)
                response = self.client.post(url, {"next": "https://fora.example/"})
                self.assertRedirects(response, reverse("viagens_cadastros:lista", args=[slug]))
                anterior.refresh_from_db()
                novo.refresh_from_db()
                self.assertFalse(anterior.is_padrao)
                self.assertTrue(novo.is_padrao)
                self.assertEqual(model.objects.filter(is_padrao=True).count(), 1)

    def test_leitor_nao_recebe_controles_nem_pode_gravar(self):
        self.client.force_login(self.criar_usuario("leitor_catalogos"))
        lista = reverse("viagens_cadastros:lista", args=["cargos"])
        self.assertNotContains(self.client.get(lista), "data-cadastro-modal")
        novo = reverse("viagens_cadastros:novo", args=["cargos"])
        self.assertEqual(self.client.post(novo, {"nome": "BLOQUEADO"}).status_code, 403)
        url = reverse("viagens_cadastros:definir_padrao", args=["cargos", self.cargo.pk])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertFalse(Cargo.objects.filter(nome="BLOQUEADO").exists())
