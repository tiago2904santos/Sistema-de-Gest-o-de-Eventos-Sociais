"""Preencher a pauta nova a partir do e-mail (release, pedido de divulgação)."""

import shutil
import tempfile
from email.message import EmailMessage
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Setor
from core.leitura.mensagem import Mensagem, ler_texto_colado

from . import preenchimento
from .models import AcaoHistorico, Publicacao, Responsavel, Unidade

User = get_user_model()

ASSUNTO = "RES: Release - Prisão por tráfico em Colombo"
CORPO = """Boa tarde,

Segue release para divulgação: a Polícia Civil do Paraná (PCPR) prendeu nesta quinta-feira (24) um homem \
de 32 anos suspeito de tráfico de drogas em Colombo, na Região Metropolitana de Curitiba. A ação foi \
coordenada pela 10ª DP de forma integrada.

Seguem fotos em anexo.

Att,
Marcos Vinicius Andrade
Delegado de Polícia
10ª Delegacia de Polícia de Curitiba
(41) 3304-5500
"""
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


def email_do_release(*, assunto=ASSUNTO, corpo=CORPO, fotos=2):
    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = "Marcos Vinicius Andrade <marcos.andrade@pc.pr.gov.br>"
    mensagem["To"] = "ascom@pc.pr.gov.br"
    mensagem["Date"] = "Thu, 24 Sep 2026 16:05:00 -0300"
    mensagem.set_content(corpo)
    for numero in range(fotos):
        mensagem.add_attachment(JPEG, maintype="image", subtype="jpeg", filename=f"foto{numero + 1}.jpg")
    return mensagem.as_bytes()


class BasePautaPorEmail(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user("gabriela", password="x", first_name="Gabriela", last_name="Souza")
        cls.usuario.setores.add(Setor.objects.get(nome="ASCOM"))
        cls.sem_modulo = User.objects.create_user("comum-pub", password="x")
        cls.gabriela = Responsavel.objects.create(nome="Gabriela")
        cls.manoela = Responsavel.objects.create(nome="Manoela")
        cls.dp10 = Unidade.objects.create(nome="10ª DP de Curitiba")
        cls.dhpp = Unidade.objects.create(nome="DHPP")

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="preencher-email-pub-")
        self.ajustes = override_settings(PREENCHER_EMAIL_PASTA=self.pasta)
        self.ajustes.enable()
        self.addCleanup(self.ajustes.disable)
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.client.force_login(self.usuario)
        self.url = reverse("publicacoes:ler_email")

    def ler_eml(self, conteudo=None):
        arquivo = SimpleUploadedFile("release.eml", conteudo or email_do_release(), content_type="message/rfc822")
        return self.client.post(self.url, {"arquivo": arquivo})

    @staticmethod
    def valores(dados):
        return {nome: campo["valor"] for nome, campo in dados["campos"].items()}

    def salvar(self, **extra):
        dados = {
            "data": "2026-09-24",
            "jornalista": self.gabriela.pk,
            "unidade": self.dp10.pk,
            "titulo": "Prisão por tráfico em Colombo",
        }
        dados.update(extra)
        return self.client.post(reverse("publicacoes:nova"), dados)


class LerEmailPautaTests(BasePautaPorEmail):
    def test_eml_preenche_a_pauta(self):
        resposta = self.ler_eml()
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        campos = self.valores(dados)
        self.assertEqual(campos, {
            "data": "2026-09-24",
            "titulo": "Prisão por tráfico em Colombo",
            "jornalista": str(self.gabriela.pk),
            "unidade": str(self.dp10.pk),
            "fonte": "Del. Marcos Vinicius Andrade",
            "inicio_pauta": "16:05",
        })
        # A unidade é sempre só sugestão (a "outra unidade" cria cadastro ao salvar).
        self.assertEqual(dados["campos"]["unidade"]["confianca"], "B")
        self.assertTrue(any("2 foto(s) (foto1.jpg, foto2.jpg)" in aviso for aviso in dados["avisos"]))
        self.assertFalse(Publicacao.objects.exists())

    def test_assunto_generico_usa_a_primeira_frase(self):
        dados = self.ler_eml(email_do_release(assunto="Release", fotos=0)).json()
        self.assertEqual(
            dados["campos"]["titulo"]["valor"],
            "A Polícia Civil do Paraná (PCPR) prendeu nesta quinta-feira (24) um homem de 32 anos suspeito de "
            "tráfico de drogas em Colombo, na Região Metropolitana de Curitiba",
        )
        self.assertEqual(dados["avisos"], [])

    def test_unidade_fora_do_cadastro_so_como_sugestao_de_outra_unidade(self):
        corpo = CORPO.replace("10ª Delegacia de Polícia de Curitiba", "3 Delegacia de Polícia de Londrina").replace(
            "pela 10ª DP de forma integrada", "pela equipe"
        )
        dados = self.ler_eml(email_do_release(corpo=corpo, fotos=0)).json()
        self.assertNotIn("unidade", dados["campos"])
        self.assertEqual(dados["campos"]["unidade_nova"]["valor"], "3ª DP de Londrina")
        self.assertEqual(dados["campos"]["unidade_nova"]["confianca"], "B")
        self.assertFalse(Unidade.objects.filter(nome__icontains="Londrina").exists())

    def test_sigla_do_cadastro_no_texto(self):
        mensagem = ler_texto_colado("A DHPP prendeu o autor do homicídio no Cajuru. Para divulgação.")
        sugestoes = preenchimento.sugestoes(mensagem)
        self.assertEqual(sugestoes["unidade"].valor, self.dhpp)

    def test_fonte_citada_no_texto_sem_assinatura(self):
        mensagem = Mensagem(corpo="Segundo o delegado Rafael Guimarães Lopes, o suspeito confessou.")
        self.assertEqual(preenchimento.sugestoes(mensagem)["fonte"].valor, "Del. Rafael Guimarães Lopes")

    def test_permissao_e_metodo(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.client.post(self.url, {"texto": CORPO}).status_code, 403)

    def test_tela_nova_tem_o_componente(self):
        resposta = self.client.get(reverse("publicacoes:nova"))
        self.assertContains(resposta, f'data-url="{self.url}"')
        self.assertContains(resposta, 'data-formulario="form-publicacao"')
        self.assertContains(resposta, 'data-substituir-padrao="data"')


class SalvarPautaComEmailTests(BasePautaPorEmail):
    def test_salvar_registra_o_email_no_historico(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        resposta = self.salvar(email_origem=token)
        publicacao = Publicacao.objects.get()
        self.assertRedirects(resposta, reverse("publicacoes:editar", args=[publicacao.pk]))
        criacao = publicacao.historico.get(acao=AcaoHistorico.CRIACAO)
        self.assertEqual(
            criacao.descricao,
            "Pauta registrada no sistema. Criada a partir do e-mail "
            "'Release - Prisão por tráfico em Colombo' de Marcos Vinicius Andrade (24/09/2026 16:05).",
        )
        self.assertFalse((Path(self.pasta) / "preencher-por-email" / f"{token}.bin").exists())
        duplicados = self.ler_eml().json()["duplicados"]
        self.assertEqual(duplicados[0]["url"], reverse("publicacoes:editar", args=[publicacao.pk]))

    def test_formulario_com_erro_mantem_o_vinculo(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        resposta = self.salvar(email_origem=token, unidade="")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, f'name="email_origem" value="{token}"')
        self.assertContains(resposta, "continua ligado a esta pauta")

    def test_sem_email_o_historico_fica_como_era(self):
        self.salvar()
        self.assertEqual(Publicacao.objects.get().historico.get().descricao, "Pauta registrada no sistema.")
