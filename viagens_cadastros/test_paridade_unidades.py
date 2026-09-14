from django.urls import reverse

from auditoria.models import LogAuditoria

from .models import Servidor, Unidade
from .permissions import GRUPO_OPERADOR
from .tests import BaseViagensTestCase


class ParidadeUnidadesTests(BaseViagensTestCase):
    def setUp(self):
        self.usuario = self.criar_usuario("unidades_paridade", GRUPO_OPERADOR)
        self.client.force_login(self.usuario)
        self.lista = reverse("viagens_cadastros:lista", args=["unidades"])

    def test_inclusao_normaliza_preserva_retorno_e_nao_move_servidores(self):
        anterior = Unidade.objects.create(nome="UNIDADE ANTERIOR")
        servidor = Servidor.objects.create(nome="SERVIDOR LOTADO", unidade=anterior)
        response = self.client.post(self.lista, {
            "nome": "  unidade de ensaio  ", "sigla": " ue ",
            "servidores": [servidor.pk], "next": "/viagens/cadastros/viaturas/novo/",
        }, follow=True)
        self.assertContains(response, "Unidade criada com sucesso.")
        self.assertContains(response, "Voltar ao servidor")
        self.assertIn("next=%2Fviagens%2Fcadastros%2Fviaturas%2Fnovo%2F", response.redirect_chain[0][0])
        nova = Unidade.objects.get(nome="UNIDADE DE ENSAIO")
        self.assertEqual(nova.sigla, "UE")
        servidor.refresh_from_db()
        self.assertEqual(servidor.unidade, anterior)
        self.assertFalse(nova.servidores.exists())
        self.assertTrue(LogAuditoria.objects.filter(usuario=self.usuario, acao="VIAGENS_CADASTRO_CRIADO").exists())
        self.assertNotContains(response, "Definir padrão")

    def test_busca_por_sigla_e_nome_sem_acentos_pagina_15(self):
        Unidade.objects.bulk_create([Unidade(nome=f"DELEGACIA {i:02}", sigla=f"AÇÃO{i:02}") for i in range(17)])
        response = self.client.get(self.lista, {"q": "acao", "page": 2, "next": "/viagens/"})
        self.assertEqual(response.context["pagina"].paginator.count, 17)
        self.assertEqual(len(response.context["itens"]), 2)
        self.assertContains(response, "DELEGACIA 16")
        self.assertNotContains(response, "DELEGACIA 00")
        self.assertIn("q=acao", response.context["querystring"])
        self.assertIn("next=%2Fviagens%2F", response.context["querystring"])
        self.assertEqual(self.client.get(self.lista, {"q": "delegacia 16"}).context["pagina"].paginator.count, 1)

    def test_duplicidade_preserva_campos_sem_gravar_e_rejeita_retorno_externo(self):
        Unidade.objects.create(nome="UNIDADE DUPLICADA")
        response = self.client.post(self.lista, {"nome": "unidade duplicada", "sigla": "UD"})
        self.assertContains(response, "Já existe uma unidade com este nome.")
        self.assertContains(response, 'value="UD"')
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(Unidade.objects.filter(nome="UNIDADE DUPLICADA").count(), 1)
        response = self.client.post(self.lista, {"nome": "SEM SIGLA", "next": "https://fora.example/"})
        self.assertRedirects(response, self.lista)
        self.assertEqual(Unidade.objects.get(nome="SEM SIGLA").sigla, "")

    def test_excluir_get_preserva_e_post_apaga_com_auditoria(self):
        unidade = Unidade.objects.create(nome="UNIDADE DESCARTÁVEL")
        url = reverse("viagens_cadastros:excluir", args=["unidades", unidade.pk])
        self.assertRedirects(self.client.get(url), self.lista)
        self.assertTrue(Unidade.objects.filter(pk=unidade.pk).exists())
        response = self.client.post(url, {"next": "/viagens/"}, follow=True)
        self.assertContains(response, "Unidade excluída com sucesso.")
        self.assertFalse(Unidade.objects.filter(pk=unidade.pk).exists())
        self.assertTrue(LogAuditoria.objects.filter(usuario=self.usuario, acao="VIAGENS_CADASTRO_EXCLUIDO").exists())

    def test_leitor_nao_recebe_acoes_nem_pode_criar_ou_excluir(self):
        unidade = Unidade.objects.create(nome="UNIDADE PROTEGIDA")
        self.client.force_login(self.criar_usuario("leitor_unidades"))
        self.assertNotContains(self.client.get(self.lista), "data-catalogo-toggle")
        self.assertNotContains(self.client.get(self.lista), 'data-catalogo-excluir ')
        self.assertEqual(self.client.post(self.lista, {"nome": "NÃO CRIAR"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("viagens_cadastros:excluir", args=["unidades", unidade.pk])).status_code, 403)
        self.assertTrue(Unidade.objects.filter(pk=unidade.pk).exists())

    def test_paginacao_sete_paginas_mantem_filtro_e_limites(self):
        Unidade.objects.bulk_create([Unidade(nome=f"PAGINAÇÃO {i:03}") for i in range(97)])
        for numero, esperadas in [(1, [1, 2, "…", 7]), (4, [1, 2, 3, 4, 5, 6, 7]), (7, [1, "…", 6, 7])]:
            with self.subTest(numero=numero):
                response = self.client.get(self.lista, {"q": "paginacao", "page": numero, "next": "/viagens/"})
                self.assertEqual(response.context["paginas_visiveis"], esperadas)
                self.assertContains(response, "q=paginacao&amp;next=%2Fviagens%2F&amp;page=")
                if numero in [1, 7]:
                    self.assertContains(response, 'aria-disabled="true"', count=1)
        # Com uma única página, o GV não mostra régua nem setas.
        response = self.client.get(self.lista, {"q": "PAGINAÇÃO 096"})
        self.assertNotContains(response, 'aria-label="Paginação"')
