"""Preencher a palestra nova a partir de um e-mail: leitura, sugestões e histórico."""

import shutil
import tempfile
from email.message import EmailMessage
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Modulo, Setor
from cadastros.models import Estado, Municipio, Regiao
from core.leitura.mensagem import ler_texto_colado
from core.leitura.tests.test_mensagem import pdf_de_linhas

from . import preenchimento
from .models import (
    AcaoHistoricoDemanda,
    CanalSolicitacao,
    DemandaEvento,
    Palestrante,
    Tema,
    TipoEventoPalestra,
)
from .permissions import CODIGO_MODULO

User = get_user_model()

ASSUNTO = "RES: Solicitação de palestra - Colégio Estadual Professor Brandão"
CORPO = """Bom dia,

O Colégio Estadual Professor Brandão, de Ponta Grossa, gostaria de solicitar uma palestra sobre crimes \
virtuais para cerca de 120 alunos do ensino médio, no dia 15/10/2026, às 14h, com término previsto às 16h.

Caso haja disponibilidade, sugerimos o investigador Carlos Alberto Pereira, que já esteve aqui.

Atenciosamente,
Maria Aparecida Souza
Diretora
Colégio Estadual Professor Brandão
(42) 99912-3456
"""
PDF_CONVITE = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)
WHATSAPP = (
    "[24/09/2026 09:10] Joana Lima: Bom dia! Aqui é da Escola Municipal Castro Alves, em Castro. "
    "Queríamos agendar um bate-papo sobre violência contra a mulher no ambiente doméstico com os pais, "
    "dia 10/10 às 19h, para umas 80 pessoas.\n"
    "[24/09/2026 09:11] Joana Lima: Meu telefone é 42 99911-2233"
)


def email_do_pedido(*, corpo=CORPO, assunto=ASSUNTO, anexo=True):
    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = "Maria Aparecida Souza <Maria.Souza@escola.pr.gov.br>"
    mensagem["To"] = "ascom@pc.pr.gov.br"
    mensagem["Date"] = "Thu, 24 Sep 2026 14:32:00 -0300"
    mensagem.set_content(corpo)
    if anexo:
        mensagem.add_attachment(PDF_CONVITE, maintype="application", subtype="pdf", filename="convite.pdf")
    return mensagem.as_bytes()


class BasePalestraPorEmail(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ascom = Setor.objects.get(sigla="ASCOM")
        cls.usuario = User.objects.create_user("ascom-palestra", password="x")
        cls.usuario.setores.add(cls.ascom)
        cls.outro_setor = Setor.objects.create(sigla="ASCOM-PAL", nome="Outra equipe de palestras")
        cls.outro_setor.modulos.add(Modulo.objects.get(codigo=CODIGO_MODULO))
        cls.outro = User.objects.create_user("outra-palestra", password="x")
        cls.outro.setores.add(cls.outro_setor)
        cls.sem_modulo = User.objects.create_user("sem-palestra", password="x")
        cls.parana = Estado.objects.get(codigo_ibge=41)
        regiao = Regiao.objects.get_or_create(nome="Região Teste")[0]
        cls.ponta_grossa = Municipio.objects.get_or_create(
            nome="Ponta Grossa", estado=cls.parana, defaults={"regiao": regiao}
        )[0]
        cls.castro = Municipio.objects.get_or_create(nome="Castro", estado=cls.parana, defaults={"regiao": regiao})[0]
        cls.crimes = Tema.objects.create(nome="Crimes virtuais")
        cls.violencia = Tema.objects.create(nome="Violência doméstica")
        cls.carlos = Palestrante.objects.create(nome="Carlos Alberto Pereira", lotacao="13ª SDP", tema_abordagem="Crimes virtuais")
        # Nome de uma palavra só não é casado: "Rafael" aparece em qualquer texto.
        Palestrante.objects.create(nome="Rafael", lotacao="DP Castro")

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="preencher-email-pal-")
        self.ajustes = override_settings(PREENCHER_EMAIL_PASTA=self.pasta)
        self.ajustes.enable()
        self.addCleanup(self.ajustes.disable)
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.client.force_login(self.usuario)
        self.url = reverse("demandas_eventos:ler_email")

    def ler_eml(self, conteudo=None):
        arquivo = SimpleUploadedFile("pedido.eml", conteudo or email_do_pedido(), content_type="message/rfc822")
        return self.client.post(self.url, {"arquivo": arquivo})

    @staticmethod
    def valores(dados):
        return {nome: campo["valor"] for nome, campo in dados["campos"].items()}

    def salvar(self, **extra):
        dados = {
            "evento": TipoEventoPalestra.PALESTRA,
            "solicitante": "Maria Aparecida Souza — Colégio Estadual Professor Brandão",
            "data_solicitacao": "2026-09-24",
            "canal_solicitacao": CanalSolicitacao.EMAIL,
        }
        dados.update(extra)
        return self.client.post(reverse("demandas_eventos:nova"), dados)


class LerEmailPalestraTests(BasePalestraPorEmail):
    def test_eml_preenche_a_palestra(self):
        resposta = self.ler_eml()
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        campos = self.valores(dados)
        self.assertEqual(campos["data_solicitacao"], "2026-09-24")
        self.assertEqual(campos["evento"], TipoEventoPalestra.PALESTRA)
        self.assertEqual(campos["data_inicio_evento"], "2026-10-15")
        self.assertNotIn("data_fim_evento", campos)  # um dia só
        self.assertEqual(campos["hora_inicio"], "14:00")
        self.assertEqual(campos["estado"], str(self.parana.pk))
        self.assertEqual(campos["municipio"], str(self.ponta_grossa.pk))
        self.assertEqual(campos["quantidade_publico"], "120")
        self.assertEqual(campos["temas"], [str(self.crimes.pk)])
        self.assertEqual(dados["campos"]["temas"]["confianca"], "M")
        # O palestrante citado pelo nome inteiro: só sugestão (a tela recomenda pelo tema).
        self.assertEqual(campos["palestrantes"], [str(self.carlos.pk)])
        self.assertEqual(dados["campos"]["palestrantes"]["confianca"], "B")
        self.assertEqual(campos["solicitante"], "Maria Aparecida Souza — Colégio Estadual Professor Brandão")
        self.assertEqual(campos["telefone"], "(42) 99912-3456")
        self.assertEqual(campos["email"], "maria.souza@escola.pr.gov.br")
        self.assertEqual(campos["canal_solicitacao"], CanalSolicitacao.EMAIL)
        self.assertNotIn("protocolo", campos)
        self.assertEqual(campos["assunto_email"], "Solicitação de palestra - Colégio Estadual Professor Brandão")
        self.assertTrue(campos["pedido_contato"].startswith("Bom dia,\n\nO Colégio Estadual Professor Brandão"))
        self.assertTrue(campos["pedido_contato"].endswith("Colégio Estadual Professor Brandão\n(42) 99912-3456"))
        self.assertEqual(dados["campos"]["descricao"]["confianca"], "B")
        self.assertTrue(campos["descricao"].startswith("O Colégio Estadual Professor Brandão"))
        # O que não tem campo vai para "Informações prévias".
        self.assertEqual(
            campos["informacoes_previas"], "Término previsto: 16:00.\nAnexos do e-mail: convite.pdf."
        )
        self.assertEqual(dados["campos"]["municipio"]["rotulo"], "Município")
        self.assertFalse(DemandaEvento.objects.exists())

    def test_sugestoes_passam_na_validacao_do_formulario(self):
        """O que a tela recebe, enviado como está, salva a palestra."""
        dados = self.ler_eml().json()
        post = {nome: campo["valor"] for nome, campo in dados["campos"].items() if campo["confianca"] != "B"}
        resposta = self.client.post(reverse("demandas_eventos:nova"), post)
        demanda = DemandaEvento.objects.get()
        self.assertRedirects(resposta, reverse("demandas_eventos:editar", args=[demanda.pk]))
        self.assertEqual(demanda.municipio, self.ponta_grossa)
        self.assertEqual(demanda.telefone, "(42) 99912-3456")
        self.assertEqual(list(demanda.temas.all()), [self.crimes])
        self.assertFalse(demanda.palestrantes.exists())

    def test_conversa_do_whatsapp_colada(self):
        dados = self.client.post(self.url, {"texto": WHATSAPP}).json()
        campos = self.valores(dados)
        self.assertEqual(campos["canal_solicitacao"], CanalSolicitacao.WHATSAPP)
        self.assertEqual(campos["evento"], TipoEventoPalestra.PALESTRA)  # bate-papo
        self.assertEqual(campos["municipio"], str(self.castro.pk))  # "em Castro": nome ambíguo com âncora
        self.assertEqual(campos["data_inicio_evento"], "2026-10-10")
        self.assertEqual(campos["hora_inicio"], "19:00")
        self.assertEqual(campos["quantidade_publico"], "80")
        self.assertEqual(campos["telefone"], "(42) 99911-2233")
        self.assertEqual(campos["solicitante"], "Joana Lima")
        self.assertNotIn("email", campos)
        # "violência … doméstico" casa pelas palavras do tema: fica como sugestão.
        self.assertEqual(campos["temas"], [str(self.violencia.pk)])
        self.assertEqual(dados["campos"]["temas"]["confianca"], "B")
        self.assertTrue(any("sábado" in aviso for aviso in dados["avisos"]))

    def test_protocolo_ancorado_muda_o_canal(self):
        corpo = CORPO.replace(
            "Caso haja disponibilidade", "O pedido também foi enviado pelo protocolo nº 26.613.666-8. Caso haja disponibilidade"
        )
        dados = self.ler_eml(email_do_pedido(corpo=corpo)).json()
        campos = self.valores(dados)
        self.assertEqual(campos["canal_solicitacao"], CanalSolicitacao.PROTOCOLO)
        self.assertEqual(campos["protocolo"], "26.613.666-8")
        self.assertTrue(any("26.613.666-8" in aviso for aviso in dados["avisos"]))

    def test_telefone_nao_vira_protocolo(self):
        dados = self.ler_eml().json()
        self.assertNotIn("protocolo", dados["campos"])

    def test_tipo_do_evento(self):
        casos = [
            ("Pedimos a participação no PCPR na Comunidade do bairro.", TipoEventoPalestra.PCPR_NA_COMUNIDADE, "M"),
            ("Convidamos a PCPR para montar um estande na feira de profissões.", TipoEventoPalestra.EVENTO, "B"),
            ("Solicitamos uma roda de conversa com os alunos.", TipoEventoPalestra.PALESTRA, "M"),
        ]
        for texto, evento, confianca in casos:
            with self.subTest(texto=texto):
                sugestao = preenchimento.sugestoes(ler_texto_colado(texto))["evento"]
                self.assertEqual((sugestao.valor, sugestao.confianca), (evento, confianca))
        self.assertNotIn("evento", preenchimento.sugestoes(ler_texto_colado("Bom dia, tudo bem?")))

    def test_o_que_nao_tem_campo_vai_para_informacoes_previas(self):
        casos = [
            ("Palestra nos dias 13, 15 e 20/10/2026 pela manhã.", "Período: manhã.\nDias citados no pedido: 13/10, 15/10 e 20/10."),
            ("A palestra será no dia 13/10/2026, das 9h às 11h30.", "Término previsto: 11:30."),
        ]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                sugestoes = preenchimento.sugestoes(ler_texto_colado(texto))
                self.assertEqual(sugestoes["informacoes_previas"].valor, esperado)
        sugestoes = preenchimento.sugestoes(ler_texto_colado(casos[0][0]))
        self.assertEqual((sugestoes["data_inicio_evento"].valor.day, sugestoes["data_fim_evento"].valor.day), (13, 20))
        self.assertNotIn("hora_inicio", sugestoes)

    def test_pdf_impresso_do_outlook(self):
        linhas = [
            "De: Maria Aparecida Souza <maria.souza@escola.pr.gov.br>",
            "Enviado em: quinta-feira, 24 de setembro de 2026 14:32",
            "Para: ASCOM <ascom@pc.pr.gov.br>",
            "Assunto: Palestra sobre crimes virtuais",
            "",
            "Bom dia, gostaríamos de uma palestra sobre crimes virtuais em Ponta Grossa no dia 15/10/2026.",
        ]
        arquivo = SimpleUploadedFile("pedido.pdf", pdf_de_linhas(linhas), content_type="application/pdf")
        campos = self.valores(self.client.post(self.url, {"arquivo": arquivo}).json())
        self.assertEqual(campos["data_solicitacao"], "2026-09-24")
        self.assertEqual(campos["assunto_email"], "Palestra sobre crimes virtuais")
        self.assertEqual(campos["municipio"], str(self.ponta_grossa.pk))
        self.assertEqual(campos["temas"], [str(self.crimes.pk)])

    def test_arquivo_recusado(self):
        resposta = self.client.post(self.url, {"arquivo": SimpleUploadedFile("pedido.docx", b"PK\x03\x04")})
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("erro", resposta.json())

    def test_permissao_e_metodo(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.client.post(self.url, {"texto": WHATSAPP}).status_code, 403)
        self.client.logout()
        resposta = self.client.post(self.url, {"texto": WHATSAPP})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta.url)

    def test_tela_nova_tem_o_componente_e_a_de_edicao_nao(self):
        resposta = self.client.get(reverse("demandas_eventos:nova"))
        self.assertContains(resposta, "data-preencher-email")
        self.assertContains(resposta, f'data-url="{self.url}"')
        self.assertContains(resposta, 'data-formulario="form-demanda"')
        self.assertContains(resposta, 'data-substituir-padrao="data_solicitacao estado evento"')
        self.salvar()
        demanda = DemandaEvento.objects.get()
        resposta = self.client.get(reverse("demandas_eventos:editar", args=[demanda.pk]))
        self.assertNotContains(resposta, "data-preencher-email")


class SalvarPalestraComEmailTests(BasePalestraPorEmail):
    def test_salvar_registra_o_email_no_historico(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        resposta = self.salvar(email_origem=token)
        demanda = DemandaEvento.objects.get()
        self.assertRedirects(resposta, reverse("demandas_eventos:editar", args=[demanda.pk]))
        criacao = demanda.historico.get(acao=AcaoHistoricoDemanda.CRIACAO)
        self.assertEqual(
            criacao.descricao,
            "Registro criado no sistema. Criada a partir do e-mail "
            "'Solicitação de palestra - Colégio Estadual Professor Brandão' de Maria Aparecida Souza "
            "(24/09/2026 14:32).",
        )
        self.assertFalse((Path(self.pasta) / "preencher-por-email" / f"{token}.bin").exists())
        # Ler o mesmo e-mail de novo avisa que ele já virou palestra — para quem enxerga a palestra.
        duplicados = self.ler_eml().json()["duplicados"]
        self.assertEqual(duplicados, [{"titulo": f"Palestra #{demanda.pk}", "url": reverse("demandas_eventos:editar", args=[demanda.pk])}])
        self.client.force_login(self.outro)
        self.assertEqual(self.ler_eml().json()["duplicados"], [])

    def test_sem_email_o_historico_fica_como_era(self):
        self.salvar()
        self.assertEqual(DemandaEvento.objects.get().historico.get().descricao, "Registro criado no sistema.")

    def test_token_de_outro_modulo_nao_vale(self):
        sessao = self.client.session
        sessao["preencher_por_email"] = {
            "c" * 32: {"modulo": "publicacoes", "nome": "x.eml", "assunto": "Outro", "remetente": "X", "enviado_em": ""}
        }
        sessao.save()
        (Path(self.pasta) / "preencher-por-email").mkdir(parents=True, exist_ok=True)
        (Path(self.pasta) / "preencher-por-email" / ("c" * 32 + ".bin")).write_bytes(email_do_pedido())
        self.salvar(email_origem="c" * 32)
        self.assertEqual(DemandaEvento.objects.get().historico.get().descricao, "Registro criado no sistema.")

    def test_formulario_com_erro_mantem_o_vinculo(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        resposta = self.salvar(email_origem=token, solicitante="")
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DemandaEvento.objects.exists())
        self.assertContains(resposta, f'name="email_origem" value="{token}"')
        self.assertContains(resposta, "continua ligado a esta palestra")

    def test_edicao_ignora_o_email(self):
        self.salvar()
        demanda = DemandaEvento.objects.get()
        token = self.ler_eml().json()["arquivo"]["token"]
        self.client.post(reverse("demandas_eventos:editar", args=[demanda.pk]), {
            "evento": TipoEventoPalestra.PALESTRA,
            "solicitante": "Outro solicitante",
            "data_solicitacao": "2026-09-24",
            "versao": str(int(demanda.atualizado_em.timestamp() * 1_000_000)),
            "email_origem": token,
        })
        descricoes = list(demanda.historico.values_list("descricao", flat=True))
        self.assertFalse(any("e-mail" in d for d in descricoes))
        # O e-mail lido continua disponível para a palestra nova que ele deve gerar.
        self.assertTrue((Path(self.pasta) / "preencher-por-email" / f"{token}.bin").exists())
