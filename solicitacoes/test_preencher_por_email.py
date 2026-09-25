"""Preencher a solicitação nova a partir de um e-mail: endpoint, anexo e histórico."""

import shutil
import tempfile
from email.message import EmailMessage
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from cadastros.models import Estado, Municipio, OrgaoResponsavel, Regiao, Servico, TipoEvento
from core.leitura.tests.test_mensagem import msg_sintetico, pdf_de_linhas

from .forms import validar_arquivo_anexo
from .models import AcaoHistorico, AnexoSolicitacao, SolicitacaoEvento

User = get_user_model()

ASSUNTO = "Solicitação de unidade móvel – Ação social em Ponta Grossa"
CORPO = """Bom dia,

A Prefeitura Municipal de Ponta Grossa, por meio da Secretaria de Assistência Social, solicita o apoio da \
Polícia Civil com a unidade móvel para emissão de carteiras de identidade (CIN) durante a Ação Social no \
Bairro Uvaranas, que será realizada nos dias 20 e 21 de outubro de 2026, das 9h às 16h, no Ginásio de \
Esportes Oscar Pereira, Rua Carlos Cavalcanti, 500.

Estimamos cerca de 300 atendimentos.

Atenciosamente,
Maria Aparecida Souza
Coordenadora de Projetos Sociais
Secretaria Municipal de Assistência Social - Ponta Grossa
(42) 3220-1000 | (42) 99876-5432
"""
PDF_OFICIO = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)
TEXTO_PARANA_EM_ACAO = """De: João Pereira <joao.pereira@toledo.pr.gov.br>
Enviado em: quinta-feira, 24 de setembro de 2026 10:15
Para: Eventos PCPR <eventos@pc.pr.gov.br>
Assunto: Paraná em Ação em Toledo

Prezados, solicitamos a participação da Polícia Civil no Paraná em Ação que acontecerá em Toledo/PR, \
no dia 17/10 (sábado), das 8h às 17h, na Praça Willy Barth. Precisamos de emissão de RG e coleta de \
digitais para cerca de 200 pessoas.

Att,
João Pereira
Assessor de Eventos
Prefeitura de Toledo
(45) 3055-8800
"""


def email_do_pedido(*, com_anexo=True):
    mensagem = EmailMessage()
    mensagem["Subject"] = ASSUNTO
    mensagem["From"] = "Maria Aparecida Souza <maria.souza@pontagrossa.pr.gov.br>"
    mensagem["To"] = "eventos@pc.pr.gov.br"
    mensagem["Date"] = "Thu, 24 Sep 2026 14:32:00 -0300"
    mensagem["Message-ID"] = "<pedido-pg@pontagrossa.pr.gov.br>"
    mensagem.set_content(CORPO)
    if com_anexo:
        mensagem.add_attachment(PDF_OFICIO, maintype="application", subtype="pdf", filename="oficio.pdf")
    return mensagem.as_bytes()


class BasePreencherPorEmail(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.parana = Estado.objects.get(codigo_ibge=41)
        regiao = Regiao.objects.get_or_create(nome="Região Teste")[0]
        cls.ponta_grossa = Municipio.objects.create(nome="Ponta Grossa", estado=cls.parana, regiao=regiao)
        cls.toledo = Municipio.objects.create(nome="Toledo", estado=cls.parana, regiao=regiao)
        Municipio.objects.create(nome="Curitiba", estado=cls.parana, regiao=regiao)
        cls.cin = Servico.objects.create(nome="Emissão de CIN")
        cls.digitais = Servico.objects.create(nome="Coleta de digitais")
        cls.iipr = OrgaoResponsavel.objects.create(nome="Instituto de Identificação do Paraná")
        cls.tipo_evento = TipoEvento.objects.get_or_create(nome="Evento")[0]
        cls.parana_em_acao = TipoEvento.objects.get_or_create(nome="Paraná em Ação")[0]
        cls.usuario = User.objects.create_user("solicitante-email", password="x")
        cls.outro = User.objects.create_user("outro-email", password="x")

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="preencher-email-")
        self.media = tempfile.mkdtemp(prefix="media-email-")
        self.ajustes = override_settings(PREENCHER_EMAIL_PASTA=self.pasta, MEDIA_ROOT=self.media)
        self.ajustes.enable()
        self.addCleanup(self.ajustes.disable)
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.addCleanup(shutil.rmtree, self.media, True)
        self.client.force_login(self.usuario)
        self.url = reverse("solicitacoes:ler_email")

    def ler(self, **dados):
        return self.client.post(self.url, dados)

    def ler_eml(self, conteudo=None, nome="pedido.eml"):
        arquivo = SimpleUploadedFile(nome, conteudo or email_do_pedido(), content_type="message/rfc822")
        return self.ler(arquivo=arquivo)

    def rascunho(self, **extra):
        dados = {"acao": "rascunho", "data_solicitacao": "2026-09-24", "tipo_operacao": "DIARIA"}
        dados.update(extra)
        return self.client.post(reverse("solicitacoes:nova"), dados)


class LerEmailTests(BasePreencherPorEmail):
    def test_eml_preenche_os_campos_do_pedido(self):
        resposta = self.ler_eml()
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        campos = {nome: campo["valor"] for nome, campo in dados["campos"].items()}
        self.assertEqual(campos["data_solicitacao"], "2026-09-24")
        self.assertEqual(campos["data_inicio_evento"], "2026-10-20")
        self.assertEqual(campos["data_fim_evento"], "2026-10-21")
        self.assertEqual(campos["estado"], str(self.parana.pk))
        self.assertEqual(campos["municipio"], str(self.ponta_grossa.pk))
        self.assertEqual(campos["local_evento"], "Ginásio de Esportes Oscar Pereira, Rua Carlos Cavalcanti, 500")
        self.assertEqual(campos["solicitante_nome"], "Maria Aparecida Souza")
        self.assertEqual(
            campos["solicitante_cargo_unidade"],
            "Coordenadora de Projetos Sociais / Secretaria Municipal de Assistência Social - Ponta Grossa",
        )
        self.assertEqual(campos["contato"], "(42) 99876-5432")  # o celular, não o fixo
        self.assertEqual(campos["servicos"], [str(self.cin.pk)])  # "Secretaria de Assistência Social" não é serviço
        self.assertEqual(campos["quantidade_cin"], "300")
        self.assertIn("Origem: e-mail de Maria Aparecida Souza em 24/09/2026 14:32.", campos["descricao_complementar"])
        self.assertNotIn("Atenciosamente", campos["descricao_complementar"])
        # Decisão interna ou genérico: só sugestão, a tela não preenche sozinha.
        confianca = {nome: campo["confianca"] for nome, campo in dados["campos"].items()}
        self.assertEqual(confianca["tipo_evento"], "B")
        self.assertEqual(campos["tipo_evento"], str(self.tipo_evento.pk))
        self.assertEqual((confianca["orgao_responsavel"], campos["orgao_responsavel"]), ("B", str(self.iipr.pk)))
        self.assertEqual((confianca["unidade_movel"], campos["unidade_movel"]), ("B", "1"))
        self.assertEqual(confianca["data_solicitacao"], "A")
        # O estado vem antes do município (a tela troca o estado e depois escolhe o município).
        nomes = list(dados["campos"])
        self.assertLess(nomes.index("estado"), nomes.index("municipio"))
        self.assertLess(nomes.index("tipo_evento"), nomes.index("solicitante_nome"))
        self.assertEqual(dados["campos"]["municipio"]["rotulo"], "Município")
        self.assertRegex(dados["arquivo"]["token"], r"^[0-9a-f]{32}$")
        self.assertEqual(dados["arquivo"]["nome"], "pedido.eml")
        self.assertEqual(dados["arquivo"]["anexos"], ["oficio.pdf"])
        self.assertEqual(dados["mensagem"]["enviado_em"], "24/09/2026 14:32")
        self.assertEqual(dados["duplicados"], [])
        # Leitura não grava nada.
        self.assertFalse(SolicitacaoEvento.objects.exists())

    def test_msg_do_outlook(self):
        conteudo = msg_sintetico(
            assunto="Pedido de atendimento em Ponta Grossa",
            corpo="Bom dia,\r\nSolicitamos emissão de RG em Ponta Grossa no dia 05/11/2026.\r\n\r\n"
                  "Atenciosamente,\r\nMaria Exemplo\r\nDiretora\r\n",
        )
        resposta = self.ler(arquivo=SimpleUploadedFile("pedido.msg", conteudo))
        self.assertEqual(resposta.status_code, 200)
        campos = resposta.json()["campos"]
        self.assertEqual(campos["municipio"]["valor"], str(self.ponta_grossa.pk))
        self.assertEqual(campos["data_inicio_evento"]["valor"], "2026-11-05")
        self.assertEqual(campos["servicos"]["valor"], [str(self.cin.pk)])

    def test_pdf_impresso_do_outlook(self):
        conteudo = pdf_de_linhas([
            "De: Maria Aparecida Souza <maria.souza@pontagrossa.pr.gov.br>",
            "Enviado em: quinta-feira, 24 de setembro de 2026 14:32",
            "Para: eventos@pc.pr.gov.br",
            "Assunto: Pedido de emissão de RG em Ponta Grossa",
            "",
            "Bom dia, solicitamos emissão de RG no dia 20/10/2026, em Ponta Grossa.",
        ])
        resposta = self.ler(arquivo=SimpleUploadedFile("pedido.pdf", conteudo, content_type="application/pdf"))
        self.assertEqual(resposta.status_code, 200)
        campos = resposta.json()["campos"]
        self.assertEqual(campos["data_solicitacao"]["valor"], "2026-09-24")
        self.assertEqual(campos["data_inicio_evento"]["valor"], "2026-10-20")
        self.assertEqual(campos["municipio"]["valor"], str(self.ponta_grossa.pk))

    def test_texto_colado_com_parana_em_acao_fixa_o_solicitante(self):
        resposta = self.ler(texto=TEXTO_PARANA_EM_ACAO)
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        campos = dados["campos"]
        self.assertEqual(campos["tipo_evento"]["valor"], str(self.parana_em_acao.pk))
        self.assertEqual(campos["tipo_evento"]["confianca"], "M")
        self.assertEqual(campos["solicitante_nome"]["valor"], "Paraná em Ação")
        self.assertEqual(campos["solicitante_cargo_unidade"]["valor"], "SEJU")
        self.assertEqual(campos["municipio"]["valor"], str(self.toledo.pk))
        self.assertEqual(campos["data_inicio_evento"]["valor"], "2026-10-17")
        self.assertEqual(campos["data_solicitacao"]["valor"], "2026-09-24")
        self.assertEqual(campos["local_evento"]["valor"], "Praça Willy Barth")
        self.assertEqual(sorted(campos["servicos"]["valor"]), sorted([str(self.cin.pk), str(self.digitais.pk)]))
        self.assertTrue(any("fim de semana" in aviso for aviso in dados["avisos"]))
        self.assertEqual(dados["arquivo"]["nome"], "texto-do-email.txt")

    def test_quinta_feira_nao_vira_tipo_feira(self):
        TipoEvento.objects.get_or_create(nome="Feira")
        texto = "Pedimos atendimento na quinta-feira, 15/10/2026, em Curitiba."
        campos = self.ler(texto=texto).json()["campos"]
        self.assertNotEqual(campos["tipo_evento"]["exibir"], "Feira")

    def test_arquivo_de_outro_tipo_e_recusado(self):
        resposta = self.ler(arquivo=SimpleUploadedFile("planilha.xlsx", b"PK\x03\x04 planilha"))
        self.assertEqual(resposta.status_code, 400)
        self.assertIn(".eml, .msg, .pdf ou .txt", resposta.json()["erro"])

    def test_conteudo_que_nao_confere_com_a_extensao_e_recusado(self):
        resposta = self.ler(arquivo=SimpleUploadedFile("pedido.eml", PDF_OFICIO))
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("não corresponde", resposta.json()["erro"])
        resposta = self.ler(arquivo=SimpleUploadedFile("pedido.pdf", b"From: x\nSubject: y\n\ncorpo"))
        self.assertEqual(resposta.status_code, 400)

    def test_arquivo_binario_e_vazio_sao_recusados(self):
        self.assertEqual(self.ler(arquivo=SimpleUploadedFile("pedido.txt", b"\x00\x01\x02" * 50)).status_code, 400)
        self.assertEqual(self.ler(arquivo=SimpleUploadedFile("pedido.eml", b"")).status_code, 400)
        resposta = self.ler(texto="   ")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("Escolha o arquivo", resposta.json()["erro"])

    @override_settings(LEITURA_EMAIL_MAX_BYTES=1024)
    def test_arquivo_acima_do_limite(self):
        resposta = self.ler_eml()
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("limite", resposta.json()["erro"])

    def test_permissao_e_metodo(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.logout()
        resposta = self.ler(texto=TEXTO_PARANA_EM_ACAO)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta.url)

    def test_leitura_nao_loga_o_conteudo(self):
        with self.assertLogs("core.preencher_por_email", level="INFO") as registro:
            self.ler_eml()
        texto = "\n".join(registro.output)
        self.assertNotIn("Maria", texto)
        self.assertNotIn("99876", texto)


class SalvarComEmailTests(BasePreencherPorEmail):
    def test_salvar_anexa_o_email_e_os_anexos_dele_e_registra_no_historico(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        self.assertTrue((Path(self.pasta) / "preencher-por-email" / f"{token}.bin").exists())

        resposta = self.rascunho(email_origem=token, solicitante_nome="Maria Aparecida Souza")
        solicitacao = SolicitacaoEvento.objects.get()
        self.assertRedirects(resposta, reverse("solicitacoes:editar", args=[solicitacao.pk]))

        anexos = list(solicitacao.anexos.order_by("pk"))
        self.assertEqual([a.nome_original for a in anexos], ["pedido.eml", "oficio.pdf"])
        self.assertEqual(anexos[0].tamanho, len(email_do_pedido()))
        self.assertEqual(anexos[0].enviado_por, self.usuario)
        with anexos[1].arquivo.open("rb") as arquivo:
            self.assertEqual(arquivo.read(), PDF_OFICIO)

        criacao = solicitacao.historico.get(acao=AcaoHistorico.CRIACAO)
        self.assertEqual(
            criacao.observacao,
            f"Criada a partir do e-mail '{ASSUNTO}' de Maria Aparecida Souza (24/09/2026 14:32)",
        )
        # O temporário sai com o registro salvo, e o token não serve de novo.
        self.assertFalse((Path(self.pasta) / "preencher-por-email" / f"{token}.bin").exists())
        self.assertNotIn(token, self.client.session.get("preencher_por_email", {}))
        self.rascunho(email_origem=token)
        self.assertEqual(SolicitacaoEvento.objects.count(), 2)
        self.assertEqual(AnexoSolicitacao.objects.count(), 2)

    def test_texto_colado_fica_anexado_como_txt(self):
        token = self.ler(texto=TEXTO_PARANA_EM_ACAO).json()["arquivo"]["token"]
        self.rascunho(email_origem=token)
        solicitacao = SolicitacaoEvento.objects.get()
        anexo = solicitacao.anexos.get()
        self.assertEqual(anexo.nome_original, "texto-do-email.txt")
        with anexo.arquivo.open("rb") as arquivo:
            self.assertIn("Paraná em Ação", arquivo.read().decode("utf-8"))
        self.assertEqual(
            solicitacao.historico.get(acao=AcaoHistorico.CRIACAO).observacao,
            "Criada a partir do e-mail 'Paraná em Ação em Toledo' de João Pereira (24/09/2026 10:15)",
        )

    def test_token_de_outra_sessao_ou_invalido_e_ignorado(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        self.client.force_login(self.outro)
        self.rascunho(email_origem=token)
        self.rascunho(email_origem="../../etc/passwd")
        self.assertEqual(SolicitacaoEvento.objects.count(), 2)
        self.assertFalse(AnexoSolicitacao.objects.exists())
        self.assertFalse(
            SolicitacaoEvento.objects.filter(historico__observacao__startswith="Criada a partir").exists()
        )

    def test_token_do_coffee_break_nao_vale_aqui(self):
        sessao = self.client.session
        sessao["preencher_por_email"] = {
            "a" * 32: {"modulo": "coffee_break", "nome": "x.eml", "assunto": "x", "remetente": "", "enviado_em": ""}
        }
        sessao.save()
        (Path(self.pasta) / "preencher-por-email").mkdir(parents=True, exist_ok=True)
        (Path(self.pasta) / "preencher-por-email" / ("a" * 32 + ".bin")).write_bytes(email_do_pedido())
        self.rascunho(email_origem="a" * 32)
        self.assertFalse(AnexoSolicitacao.objects.exists())

    def test_formulario_com_erro_mantem_o_vinculo_com_o_email(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        resposta = self.client.post(reverse("solicitacoes:nova"), {"acao": "enviar", "email_origem": token})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, f'name="email_origem" value="{token}"')
        self.assertFalse(SolicitacaoEvento.objects.exists())
        self.assertTrue((Path(self.pasta) / "preencher-por-email" / f"{token}.bin").exists())

    def test_email_ja_usado_aparece_como_duplicado(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        self.rascunho(email_origem=token)
        solicitacao = SolicitacaoEvento.objects.get()
        duplicados = self.ler_eml().json()["duplicados"]
        self.assertEqual(
            duplicados,
            [{"titulo": f"Solicitação #{solicitacao.pk}", "url": reverse("solicitacoes:editar", args=[solicitacao.pk])}],
        )
        # Quem não vê a solicitação não fica sabendo dela.
        self.client.force_login(self.outro)
        self.assertEqual(self.ler_eml().json()["duplicados"], [])

    def test_tela_nova_tem_o_componente(self):
        resposta = self.client.get(reverse("solicitacoes:nova"))
        self.assertContains(resposta, "data-preencher-email")
        self.assertContains(resposta, f'data-url="{self.url}"')
        self.assertContains(resposta, 'data-formulario="form-solicitacao"')
        self.assertContains(resposta, "js/preencher-por-email.js")
        self.assertContains(resposta, ".eml,.msg,.txt")  # o anexo comum também aceita o e-mail


class AnexoDeEmailTests(TestCase):
    def arquivo(self, nome, dados):
        return ContentFile(dados, name=nome)

    def test_eml_txt_e_msg_de_verdade_sao_aceitos(self):
        self.assertIsNone(validar_arquivo_anexo(self.arquivo("pedido.eml", email_do_pedido())))
        self.assertIsNone(validar_arquivo_anexo(self.arquivo("pedido.txt", "Pedido de evento em Toledo.".encode())))
        self.assertIsNone(validar_arquivo_anexo(self.arquivo("pedido.msg", msg_sintetico(corpo="Pedido."))))

    def test_conteudo_que_nao_confere_e_recusado(self):
        self.assertIsNotNone(validar_arquivo_anexo(self.arquivo("pedido.eml", b"so um texto qualquer")))
        self.assertIsNotNone(validar_arquivo_anexo(self.arquivo("pedido.eml", PDF_OFICIO)))
        self.assertIsNotNone(validar_arquivo_anexo(self.arquivo("pedido.txt", b"\x00\x01binario")))
        self.assertIsNotNone(validar_arquivo_anexo(self.arquivo("pedido.msg", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600)))

    def test_msg_renomeado_para_doc_nao_passa(self):
        erro = validar_arquivo_anexo(self.arquivo("oficio.doc", msg_sintetico(corpo="Pedido.")))
        self.assertIn("não corresponde", erro)
