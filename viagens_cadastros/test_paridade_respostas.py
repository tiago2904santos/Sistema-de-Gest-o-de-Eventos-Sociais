from unittest.mock import patch
from html import unescape
import re

from django.db.models import ProtectedError
from django.urls import reverse

from auditoria.models import LogAuditoria

from .models import Servidor, Viatura
from .permissions import GRUPO_OPERADOR
from .tests import BaseViagensTestCase


class RespostasCadastrosTests(BaseViagensTestCase):
    def setUp(self):
        self.usuario = self.criar_usuario("respostas_cadastros", GRUPO_OPERADOR)
        self.client.force_login(self.usuario)

    def test_servidor_criado_e_atualizado_com_mensagens_e_retorno_corretos(self):
        novo = reverse("viagens_cadastros:novo", args=["servidores"])
        response = self.client.post(novo, {"nome": "PESSOA DE ENSAIO"}, follow=True)
        self.assertContains(response, "Servidor salvo como rascunho. Complete cargo e CPF quando possível.")
        servidor = Servidor.objects.get(nome="PESSOA DE ENSAIO")
        editar = reverse("viagens_cadastros:editar", args=["servidores", servidor.pk])
        dados = {"nome": servidor.nome, "cargo": self.cargo.pk, "cpf": "52998224725", "rg": "123456789", "next": "/viagens/"}
        response = self.client.post(editar, dados, follow=True)
        self.assertContains(response, "Servidor atualizado com sucesso.")
        self.assertEqual(response.redirect_chain[0][0], "/viagens/")
        servidor.refresh_from_db()
        self.assertEqual(servidor.status, Servidor.Status.COMPLETO)
        servidor.delete()
        response = self.client.post(novo, {**dados, "next": ""}, follow=True)
        self.assertContains(response, "Servidor criado com sucesso.")

    def test_servidor_invalido_preserva_valor_e_resumo_sem_mensagem_duplicada(self):
        url = reverse("viagens_cadastros:novo", args=["servidores"])
        response = self.client.post(url, {"nome": "NÃO GRAVAR", "cpf": "11111111111"})
        self.assertContains(response, "Corrija antes de continuar", count=1)
        self.assertContains(response, "campo que precisa ser corrigido")
        self.assertContains(response, 'value="NÃO GRAVAR"')
        self.assertNotContains(response, "Corrija os campos destacados para continuar.")
        self.assertFalse(Servidor.objects.filter(nome="NÃO GRAVAR").exists())

    def test_exclusao_servidor_preserva_next_e_auditoria_e_get_nao_remove(self):
        servidor = Servidor.objects.create(nome="EXCLUIR ENSAIO")
        url = reverse("viagens_cadastros:excluir", args=["servidores", servidor.pk])
        retorno = "/viagens/cadastros/viaturas/novo/"
        lista = reverse("viagens_cadastros:lista", args=["servidores"])
        pagina = self.client.get(lista, {"next": retorno, "q": servidor.nome})
        link = re.search(r'<button[^>]*data-delete-url="([^"]+)"[^>]*data-catalogo-excluir', pagina.content.decode())
        self.assertIsNotNone(link)
        # O diálogo copia a URL real do botão; não injeta next no corpo do POST.
        url = unescape(link.group(1))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Servidor.objects.filter(pk=servidor.pk).exists())
        response = self.client.post(url, follow=True)
        self.assertIn("next=%2Fviagens%2Fcadastros%2Fviaturas%2Fnovo%2F", response.redirect_chain[0][0])
        self.assertContains(response, "Servidor excluído com sucesso.")
        self.assertFalse(Servidor.objects.filter(pk=servidor.pk).exists())
        self.assertEqual(LogAuditoria.objects.filter(usuario=self.usuario, acao="VIAGENS_CADASTRO_EXCLUIDO").count(), 1)

    def test_viatura_tem_confirmacao_direta_e_exclusao_retorna_lista(self):
        viatura = Viatura.objects.create(placa="AAA1234")
        url = reverse("viagens_cadastros:excluir", args=["viaturas", viatura.pk])
        response = self.client.get(url)
        self.assertTemplateUsed(response, "pages/viagens_cadastros/viaturas/confirmar_exclusao.html")
        self.assertContains(response, "Excluir viatura?")
        self.assertContains(response, "AAA1234")
        self.assertTrue(Viatura.objects.filter(pk=viatura.pk).exists())
        response = self.client.post(url, {"next": "/viagens/"}, follow=True)
        self.assertEqual(response.redirect_chain[0][0], reverse("viagens_cadastros:lista", args=["viaturas"]))
        self.assertContains(response, "Viatura excluída com sucesso.")
        self.assertFalse(Viatura.objects.filter(pk=viatura.pk).exists())

    def test_vinculo_concorrente_impede_exclusao_sem_auditoria_de_sucesso(self):
        viatura = Viatura.objects.create(placa="BBB1234")
        url = reverse("viagens_cadastros:excluir", args=["viaturas", viatura.pk])
        with patch.object(Viatura, "delete", side_effect=ProtectedError("Novo vínculo", {viatura})):
            response = self.client.post(url, follow=True)
        self.assertContains(response, "Não foi possível excluir este cadastro porque ele está vinculado a outros registros.")
        self.assertTrue(Viatura.objects.filter(pk=viatura.pk).exists())
        self.assertFalse(LogAuditoria.objects.filter(usuario=self.usuario, acao="VIAGENS_CADASTRO_EXCLUIDO").exists())
