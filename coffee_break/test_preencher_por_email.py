"""Preencher a solicitação nova de coffee break a partir de um e-mail."""

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

from .models import (
    AcaoHistoricoCoffeeBreak,
    ContratoCoffeeBreak,
    Fornecedor,
    LoteCoffeeBreak,
    SolicitacaoCoffeeBreak,
)

User = get_user_model()

ASSUNTO = "RES: Solicitação de coffee break – Ciclo de Palestras 1ª DP Curitiba"
CORPO = """Boa tarde,

Solicitamos coffee break para 60 participantes do Ciclo de Palestras, que será realizado no dia \
08/10/2026, em Curitiba, com intervalo às 10h.

Local de entrega: Auditório da 1ª DP - Rua José Loureiro, 376 - Centro - Curitiba
Responsável pelo recebimento: Tadeu Silva (41) 99988-6010

Atenciosamente,
Carlos Menezes
Delegado de Polícia
1ª Delegacia de Polícia de Curitiba
(41) 3304-5500
"""
TEXTO_PERIODO = """Olá! Precisamos de um coffee break para o Encontro Regional em Ponta Grossa, de 20 a 22 de \
outubro de 2026, para cerca de 150 pessoas. O café deve ser servido às 15h30 no Salão Nobre da Prefeitura.

Obrigado,
Ana Paula Lima
Assessora
Prefeitura de Ponta Grossa
42 99111-2222
"""


def email_do_pedido(corpo=CORPO):
    mensagem = EmailMessage()
    mensagem["Subject"] = ASSUNTO
    mensagem["From"] = "Carlos Menezes <carlos.menezes@pc.pr.gov.br>"
    mensagem["To"] = "ascom@pc.pr.gov.br"
    mensagem["Date"] = "Thu, 24 Sep 2026 14:32:00 -0300"
    mensagem.set_content(corpo)
    return mensagem.as_bytes()


class BaseCoffeePorEmail(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ascom = User.objects.create_user("ascom-email", password="x")
        cls.ascom.setores.add(Setor.objects.get(nome="ASCOM"))
        cls.sem_modulo = User.objects.create_user("comum-email", password="x")
        fornecedor = Fornecedor.objects.create(razao_social="PADARIA FAVO E MEL LTDA", cnpj="35014719000166")
        contrato = ContratoCoffeeBreak.objects.create(fornecedor=fornecedor, numero="0762/2024")
        cls.lote = LoteCoffeeBreak.objects.create(
            contrato=contrato, numero=1, exercicio="2026", quantidade_total=100
        )
        parana = Estado.objects.get(codigo_ibge=41)
        regiao = Regiao.objects.get_or_create(nome="Região Teste")[0]
        cls.curitiba = Municipio.objects.get_or_create(nome="Curitiba", estado=parana, defaults={"regiao": regiao})[0]
        cls.ponta_grossa = Municipio.objects.create(nome="Ponta Grossa", estado=parana, regiao=regiao)
        cls.lote.municipios.add(cls.curitiba)

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="preencher-email-cb-")
        self.ajustes = override_settings(PREENCHER_EMAIL_PASTA=self.pasta)
        self.ajustes.enable()
        self.addCleanup(self.ajustes.disable)
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.client.force_login(self.ascom)
        self.url = reverse("coffee_break:ler_email")

    def ler_eml(self, conteudo=None):
        arquivo = SimpleUploadedFile("pedido.eml", conteudo or email_do_pedido(), content_type="message/rfc822")
        return self.client.post(self.url, {"arquivo": arquivo})

    def salvar(self, **extra):
        dados = {
            "municipio": self.curitiba.pk,
            "data_solicitacao": "2026-09-24",
            "numero": "",
            "descricao_evento": "Ciclo de Palestras 1ª DP Curitiba",
            "quantidade": "60",
            "data_inicio_evento": "2026-10-08",
        }
        dados.update(extra)
        return self.client.post(reverse("coffee_break:nova"), dados)


class LerEmailCoffeeTests(BaseCoffeePorEmail):
    def test_eml_preenche_a_etapa_1(self):
        resposta = self.ler_eml()
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        campos = {nome: campo["valor"] for nome, campo in dados["campos"].items()}
        self.assertEqual(campos, {
            "data_solicitacao": "2026-09-24",
            "municipio": str(self.curitiba.pk),
            "descricao_evento": "Ciclo de Palestras 1ª DP Curitiba",
            "quantidade": "60",
            "data_inicio_evento": "2026-10-08",
            "horario_evento": "10:00",
            "local_entrega": "Auditório da 1ª DP - Rua José Loureiro, 376 - Centro - Curitiba",
            "responsavel_recebimento": "Tadeu Silva (41) 99988-6010",
        })
        # O número da OS é da numeração única: nunca vem do e-mail.
        self.assertNotIn("numero", dados["campos"])
        self.assertEqual(dados["campos"]["local_entrega"]["confianca"], "A")
        self.assertEqual(dados["avisos"], [])
        self.assertEqual(dados["arquivo"]["anexos"], [])  # o coffee break não guarda o original como anexo
        self.assertFalse(SolicitacaoCoffeeBreak.objects.exists())

    def test_texto_colado_com_periodo_e_municipio_sem_lote(self):
        resposta = self.client.post(self.url, {"texto": TEXTO_PERIODO})
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        campos = {nome: campo["valor"] for nome, campo in dados["campos"].items()}
        # Uma data só por OS: o primeiro dia, e o período vira aviso.
        self.assertEqual(campos["data_inicio_evento"], "2026-10-20")
        self.assertEqual(dados["campos"]["data_inicio_evento"]["confianca"], "M")
        self.assertNotIn("data_fim_evento", campos)
        self.assertNotIn("periodo_evento_texto", campos)
        self.assertTrue(any("mais de um dia" in aviso for aviso in dados["avisos"]))
        self.assertTrue(any("Nenhum lote ativo atende Ponta Grossa" in aviso for aviso in dados["avisos"]))
        self.assertEqual(campos["municipio"], str(self.ponta_grossa.pk))
        self.assertEqual(campos["quantidade"], "150")
        self.assertEqual(campos["horario_evento"], "15:30")
        self.assertEqual(campos["local_entrega"], "Salão Nobre da Prefeitura")
        self.assertEqual(campos["descricao_evento"], "Encontro Regional - Ponta Grossa")
        self.assertEqual(campos["responsavel_recebimento"], "Ana Paula Lima (42) 99111-2222")
        self.assertNotIn("data_solicitacao", campos)  # texto sem cabeçalho: a data fica a da tela

    def test_falta_de_saldo_vira_aviso_na_leitura(self):
        SolicitacaoCoffeeBreak.objects.create(
            lote=self.lote, descricao_evento="Outro evento", quantidade=80, criado_por=self.ascom
        )
        dados = self.ler_eml().json()
        self.assertTrue(any("tem saldo de 20 unidade(s) e o pedido é de 60" in aviso for aviso in dados["avisos"]))

    def test_arquivo_invalido(self):
        resposta = self.client.post(self.url, {"arquivo": SimpleUploadedFile("pedido.doc", b"\xd0\xcf\x11\xe0")})
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("erro", resposta.json())

    def test_permissao_do_modulo(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.client.post(self.url, {"texto": TEXTO_PERIODO}).status_code, 403)
        self.client.logout()
        resposta = self.client.post(self.url, {"texto": TEXTO_PERIODO})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta.url)

    def test_tela_nova_tem_o_componente(self):
        resposta = self.client.get(reverse("coffee_break:nova"))
        self.assertContains(resposta, "data-preencher-email")
        self.assertContains(resposta, 'data-formulario="form-coffee-break"')
        self.assertContains(resposta, 'data-substituir-padrao="data_solicitacao"')


class SalvarCoffeeComEmailTests(BaseCoffeePorEmail):
    def test_salvar_registra_o_email_no_historico(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        resposta = self.salvar(email_origem=token)
        self.assertRedirects(resposta, reverse("coffee_break:solicitacoes"))
        solicitacao = SolicitacaoCoffeeBreak.objects.get()
        criacao = solicitacao.historico.get(acao=AcaoHistoricoCoffeeBreak.CRIACAO)
        self.assertEqual(
            criacao.descricao,
            "Solicitação registrada no sistema. Criada a partir do e-mail "
            "'Solicitação de coffee break – Ciclo de Palestras 1ª DP Curitiba' de Carlos Menezes (24/09/2026 14:32).",
        )
        self.assertFalse((Path(self.pasta) / "preencher-por-email" / f"{token}.bin").exists())
        # Ler o mesmo e-mail de novo avisa que ele já virou solicitação.
        duplicados = self.ler_eml().json()["duplicados"]
        self.assertEqual(duplicados[0]["url"], reverse("coffee_break:editar", args=[solicitacao.pk]))

    def test_sem_email_o_historico_fica_como_era(self):
        self.salvar()
        criacao = SolicitacaoCoffeeBreak.objects.get().historico.get()
        self.assertEqual(criacao.descricao, "Solicitação registrada no sistema.")

    def test_token_das_solicitacoes_de_evento_nao_vale_aqui(self):
        sessao = self.client.session
        sessao["preencher_por_email"] = {
            "b" * 32: {"modulo": "solicitacoes", "nome": "x.eml", "assunto": "Outro", "remetente": "X", "enviado_em": ""}
        }
        sessao.save()
        (Path(self.pasta) / "preencher-por-email").mkdir(parents=True, exist_ok=True)
        (Path(self.pasta) / "preencher-por-email" / ("b" * 32 + ".bin")).write_bytes(email_do_pedido())
        self.salvar(email_origem="b" * 32)
        self.assertEqual(SolicitacaoCoffeeBreak.objects.get().historico.get().descricao, "Solicitação registrada no sistema.")

    def test_erro_de_saldo_mantem_o_vinculo(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        resposta = self.salvar(email_origem=token, quantidade="101")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "acima do saldo")
        self.assertContains(resposta, f'name="email_origem" value="{token}"')
