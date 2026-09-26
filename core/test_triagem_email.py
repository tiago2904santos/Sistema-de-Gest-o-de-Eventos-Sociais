"""Triagem do e-mail na página inicial: ler, decidir o módulo e abrir a tela já preenchida."""

import shutil
import tempfile
from email.message import EmailMessage
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Setor
from cadastros.models import Estado, Municipio, Regiao
from core import preencher_por_email as pe

User = get_user_model()


def email(assunto, corpo, de="Maria Exemplo <maria@escola.exemplo>"):
    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = de
    mensagem["To"] = "ascom@pc.pr.gov.br"
    mensagem["Date"] = "Thu, 24 Sep 2026 14:32:00 -0300"
    mensagem.set_content(corpo)
    return mensagem.as_bytes()


PALESTRA = email(
    "Solicitação de palestra",
    "Bom dia, o Colégio Estadual Exemplo, de Ponta Grossa, pede uma palestra sobre crimes virtuais "
    "para 120 alunos no dia 15/10/2026 às 14h.\n\nAtenciosamente,\nMaria Exemplo\nDiretora\n(42) 99912-3456",
)
SEM_SINAL = email("Bom dia", "Segue em anexo o ofício conforme conversado. Obrigada.")


class BaseTriagem(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ascom = User.objects.create_user("ascom-triagem", password="x")
        cls.ascom.setores.add(Setor.objects.get(sigla="ASCOM"))
        cls.comum = User.objects.create_user("comum-triagem", password="x")
        parana = Estado.objects.get(codigo_ibge=41)
        regiao = Regiao.objects.get_or_create(nome="Região Teste")[0]
        Municipio.objects.get_or_create(nome="Ponta Grossa", estado=parana, defaults={"regiao": regiao})

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="triagem-email-")
        ajustes = override_settings(PREENCHER_EMAIL_PASTA=self.pasta)
        ajustes.enable()
        self.addCleanup(ajustes.disable)
        self.addCleanup(shutil.rmtree, self.pasta, True)

    def ler(self, conteudo, nome="pedido.eml"):
        return self.client.post(reverse("core:triagem_ler"), {"arquivo": SimpleUploadedFile(nome, conteudo)})


class PaginaInicialTests(BaseTriagem):
    def test_faixa_aparece_para_quem_tem_modulo_que_le_email(self):
        self.client.force_login(self.ascom)
        resposta = self.client.get(reverse("core:home"))
        self.assertContains(resposta, "Solte o e-mail aqui")
        self.assertContains(resposta, reverse("core:triagem_ler"))

    def test_usuario_comum_tambem_ve_a_faixa_pelos_eventos_sociais(self):
        self.client.force_login(self.comum)
        self.assertContains(self.client.get(reverse("core:home")), "Solte o e-mail aqui")

    def test_exige_login_e_post(self):
        self.assertEqual(self.client.post(reverse("core:triagem_ler")).status_code, 302)
        self.client.force_login(self.ascom)
        self.assertEqual(self.client.get(reverse("core:triagem_ler")).status_code, 405)


class LerNaPaginaInicialTests(BaseTriagem):
    def test_palestra_decide_sozinha_e_aponta_a_tela_com_o_token(self):
        self.client.force_login(self.ascom)
        dados = self.ler(PALESTRA).json()
        self.assertEqual(dados["sugerido"], "demandas_eventos")
        self.assertTrue(dados["decidir"])
        token = dados["token"]
        sugerido = dados["candidatos"][0]
        self.assertEqual(sugerido["modulo"], "demandas_eventos")
        self.assertEqual(sugerido["url"], reverse("core:triagem_encaminhar") + f"?token={token}&modulo=demandas_eventos")
        # O encaminhar passa o e-mail para o módulo e abre a tela com o token.
        resposta = self.client.get(sugerido["url"])
        self.assertRedirects(resposta, reverse("demandas_eventos:nova") + f"?email_origem={token}", fetch_redirect_response=False)
        self.assertEqual(self.client.session["preencher_por_email"][token]["modulo"], "demandas_eventos")
        self.assertIn("palestra (assunto)", sugerido["sinais"])
        self.assertEqual(dados["resumo"]["quando"], "15/10/2026")
        self.assertEqual(dados["resumo"]["remetente"], "Maria Exemplo")
        # Os outros módulos da pessoa vêm como opção, sem sinal.
        modulos = [c["modulo"] for c in dados["candidatos"]]
        self.assertIn("coffee_break", modulos)
        self.assertIn("solicitacoes", modulos)
        self.assertTrue((Path(self.pasta) / "preencher-por-email" / f"{token}.bin").exists())

    def test_sem_sinal_nao_decide_e_lista_os_modulos_do_usuario(self):
        self.client.force_login(self.ascom)
        dados = self.ler(SEM_SINAL).json()
        self.assertFalse(dados["decidir"])
        self.assertEqual(dados["sugerido"], "")
        self.assertGreaterEqual(len(dados["candidatos"]), 2)
        self.assertTrue(any("não diz a data do evento" in a for a in dados["resumo"]["avisos"]))

    def test_usuario_comum_so_pode_ir_para_eventos_sociais(self):
        self.client.force_login(self.comum)
        dados = self.ler(PALESTRA).json()
        self.assertEqual([c["modulo"] for c in dados["candidatos"]], ["solicitacoes"])
        self.assertFalse(dados["decidir"])

    def test_arquivo_recusado(self):
        self.client.force_login(self.ascom)
        resposta = self.ler(b"nada", nome="pedido.exe")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("erro", resposta.json())


class AbrirATelaComOEmailTests(BaseTriagem):
    def test_tela_nova_le_o_token_sozinha_e_oferece_os_outros_modulos(self):
        self.client.force_login(self.ascom)
        token = self.ler(PALESTRA).json()["token"]
        resposta = self.client.get(reverse("demandas_eventos:nova") + f"?email_origem={token}")
        self.assertContains(resposta, f'data-pe-auto="{token}"')
        self.assertContains(resposta, f'name="email_origem" value="{token}"')
        # A leitura pelo token: sugestões da palestra e o atalho para os outros módulos.
        dados = self.client.post(reverse("demandas_eventos:ler_email"), {"token": token}).json()
        self.assertEqual(dados["campos"]["data_inicio_evento"]["valor"], "2026-10-15")
        self.assertEqual(dados["arquivo"]["token"], token)
        outros = {o["modulo"]: o["url"] for o in dados["outros_modulos"]}
        self.assertNotIn("demandas_eventos", outros)
        self.assertIn("coffee_break", outros)
        self.assertEqual(outros["coffee_break"], reverse("core:triagem_encaminhar") + f"?token={token}&modulo=coffee_break")
        # O token agora é da palestra: a tela de coffee break não o aceita como pendente…
        self.assertEqual(self.client.session["preencher_por_email"][token]["modulo"], "demandas_eventos")
        self.assertNotContains(self.client.get(reverse("coffee_break:nova") + f"?email_origem={token}"), "data-pe-auto")
        # …mas o encaminhar (o clique em "abrir como coffee break") passa o e-mail para lá.
        resposta = self.client.get(outros["coffee_break"])
        self.assertRedirects(resposta, reverse("coffee_break:nova") + f"?email_origem={token}", fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("coffee_break:nova") + f"?email_origem={token}"), f'data-pe-auto="{token}"')

    def test_token_invalido_ou_de_outra_sessao_nao_abre_nada(self):
        self.client.force_login(self.ascom)
        resposta = self.client.get(reverse("demandas_eventos:nova") + "?email_origem=" + "c" * 32)
        self.assertNotContains(resposta, "data-pe-auto")
        resposta = self.client.post(reverse("demandas_eventos:ler_email"), {"token": "c" * 32})
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("página inicial", resposta.json()["erro"])
        resposta = self.client.get(reverse("core:triagem_encaminhar"), {"token": "c" * 32, "modulo": "coffee_break"})
        self.assertRedirects(resposta, reverse("core:home"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("core:triagem_encaminhar"), {"token": "c" * 32, "modulo": "x"}).status_code, 400)

    def test_encaminhar_respeita_os_modulos_do_usuario(self):
        self.client.force_login(self.comum)
        token = self.ler(PALESTRA).json()["token"]
        resposta = self.client.get(reverse("core:triagem_encaminhar"), {"token": token, "modulo": "demandas_eventos"})
        self.assertEqual(resposta.status_code, 400)
        resposta = self.client.get(reverse("core:triagem_encaminhar"), {"token": token, "modulo": "solicitacoes"})
        self.assertRedirects(resposta, reverse("solicitacoes:nova") + f"?email_origem={token}", fetch_redirect_response=False)
