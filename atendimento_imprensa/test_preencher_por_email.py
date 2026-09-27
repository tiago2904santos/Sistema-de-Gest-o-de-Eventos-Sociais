"""Preencher o atendimento novo a partir do e-mail do jornalista."""

import datetime as dt
import shutil
import tempfile
from email.message import EmailMessage
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import Setor
from core.equipe import integrante_do_usuario

from .models import AcaoHistorico, Atendimento, Responsavel, SituacaoAtendimento, Veiculo

User = get_user_model()

ASSUNTO = "ENC: Pedido de posicionamento - golpe do falso advogado"
CORPO = """Olá, boa tarde!

Estou produzindo uma matéria sobre o aumento de golpes do falso advogado em Curitiba. Gostaria de um \
posicionamento da Polícia Civil e, se possível, uma entrevista com o delegado responsável.

Preciso do retorno até às 17h de hoje, pois a matéria vai ao ar no Boa Noite Paraná.

Obrigada,
Juliana Ramos
Repórter | RPC Curitiba
(41) 99876-5432
"""


def email_do_jornalista(*, corpo=CORPO, remetente="Juliana Ramos <Juliana.Ramos@rpc.com.br>"):
    mensagem = EmailMessage()
    mensagem["Subject"] = ASSUNTO
    mensagem["From"] = remetente
    mensagem["To"] = "imprensa@pc.pr.gov.br"
    mensagem["Date"] = "Thu, 24 Sep 2026 14:32:00 -0300"
    mensagem.set_content(corpo)
    return mensagem.as_bytes()


class BaseAtendimentoPorEmail(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user("mariana.costa", password="x", first_name="Mariana", last_name="Costa")
        cls.usuario.setores.add(Setor.objects.get(nome="ASCOM"))
        cls.sem_modulo = User.objects.create_user("comum-imprensa", password="x")
        cls.mariana = Responsavel.objects.create(nome="Mariana")
        cls.joao = Responsavel.objects.create(nome="João P")
        cls.rpc = Veiculo.objects.create(nome="RPC")
        cls.band = Veiculo.objects.create(nome="Band")

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="preencher-email-imp-")
        self.ajustes = override_settings(PREENCHER_EMAIL_PASTA=self.pasta)
        self.ajustes.enable()
        self.addCleanup(self.ajustes.disable)
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.client.force_login(self.usuario)
        self.url = reverse("atendimento_imprensa:ler_email")

    def ler_eml(self, conteudo=None):
        arquivo = SimpleUploadedFile("pedido.eml", conteudo or email_do_jornalista(), content_type="message/rfc822")
        return self.client.post(self.url, {"arquivo": arquivo})

    @staticmethod
    def valores(dados):
        return {nome: campo["valor"] for nome, campo in dados["campos"].items()}

    def salvar(self, **extra):
        dados = {"data": "2026-09-24", "horario": "14:32", "jornalista": "Juliana Ramos", "pedido": "Posicionamento"}
        dados.update(extra)
        return self.client.post(reverse("atendimento_imprensa:novo"), dados)


class LerEmailAtendimentoTests(BaseAtendimentoPorEmail):
    def test_eml_preenche_o_atendimento(self):
        resposta = self.ler_eml()
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        campos = self.valores(dados)
        self.assertEqual(campos["data"], "2026-09-24")
        self.assertEqual(campos["horario"], "14:32")
        self.assertEqual(campos["contato"], "juliana.ramos@rpc.com.br / (41) 99876-5432")
        self.assertEqual(
            campos["pedido"],
            "Assunto: Pedido de posicionamento - golpe do falso advogado\n\n"
            + CORPO.split("\n\nObrigada,")[0]
            + "\n\nPrazo pedido: até 17:00 de 24/09/2026.",
        )
        self.assertEqual(campos["deadline"], "2026-09-24")
        self.assertEqual(dados["campos"]["deadline"]["exibir"], "24/09/2026 até 17:00")
        self.assertEqual(campos["responsavel"], str(self.mariana.pk))
        # Jornalista nunca atendido: só sugestão, para conferir a grafia.
        self.assertEqual(campos["jornalista"], "Juliana Ramos")
        self.assertEqual(dados["campos"]["jornalista"]["confianca"], "B")
        # O veículo do cadastro, pela assinatura — também só sugestão.
        self.assertEqual(campos["veiculo"], str(self.rpc.pk))
        self.assertEqual(dados["campos"]["veiculo"]["confianca"], "B")
        self.assertNotIn("veiculo_novo", campos)
        # Fontes e resposta são o que acontece depois: nunca vêm do e-mail.
        for campo in ("fonte", "resposta", "horario_resposta", "responsavel_resposta", "inicio_pedido"):
            self.assertNotIn(campo, campos)
        self.assertFalse(Atendimento.objects.exists())

    def test_jornalista_ja_atendido_preenche_com_a_grafia_do_historico(self):
        Atendimento.objects.create(
            data=dt.date(2026, 8, 1), jornalista="Juliana Ramos", pedido="Outro pedido",
            situacao=SituacaoAtendimento.EM_ANDAMENTO,
        )
        dados = self.ler_eml(email_do_jornalista(corpo=CORPO.replace("Juliana Ramos\n", "JULIANA RAMOS\n"))).json()
        self.assertEqual(dados["campos"]["jornalista"]["valor"], "Juliana Ramos")
        self.assertEqual(dados["campos"]["jornalista"]["confianca"], "M")

    def test_veiculo_fora_do_cadastro_so_como_sugestao_de_outro_veiculo(self):
        corpo = CORPO.replace("Repórter | RPC Curitiba", "Produtora\nRádio Clube Paranaense")
        dados = self.ler_eml(email_do_jornalista(corpo=corpo, remetente="Juliana <juliana@gmail.com>")).json()
        self.assertNotIn("veiculo", dados["campos"])
        self.assertEqual(dados["campos"]["veiculo_novo"]["valor"], "Rádio Clube Paranaense")
        self.assertEqual(dados["campos"]["veiculo_novo"]["confianca"], "B")
        self.assertFalse(Veiculo.objects.filter(nome__icontains="Clube").exists())

    def test_veiculo_pelo_dominio_aprendido_do_historico(self):
        Atendimento.objects.create(
            data=dt.date(2026, 8, 1), jornalista="Pedro", pedido="x", veiculo=self.band,
            contato="pedro@bandab.com.br", situacao=SituacaoAtendimento.EM_ANDAMENTO,
        )
        corpo = CORPO.replace("Repórter | RPC Curitiba\n", "")
        dados = self.ler_eml(email_do_jornalista(corpo=corpo, remetente="Juliana <juliana@bandab.com.br>")).json()
        self.assertEqual(dados["campos"]["veiculo"]["valor"], str(self.band.pk))
        self.assertIn("@bandab.com.br", dados["campos"]["veiculo"]["trecho"])

    def test_texto_colado_sem_cabecalho(self):
        texto = "Oi, sou repórter da Band e preciso de uma nota sobre a operação de hoje até amanhã às 10h."
        dados = self.client.post(self.url, {"texto": texto}).json()
        campos = self.valores(dados)
        self.assertEqual(campos["veiculo"], str(self.band.pk))
        self.assertNotIn("data", campos)  # sem data no texto: fica a da tela
        self.assertNotIn("horario", campos)
        self.assertIn("deadline", campos)
        self.assertIn("Prazo pedido: até 10:00", campos["pedido"])

    def test_permissao_e_metodo(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.client.post(self.url, {"texto": CORPO}).status_code, 403)

    def test_tela_nova_tem_o_componente(self):
        resposta = self.client.get(reverse("atendimento_imprensa:novo"))
        self.assertContains(resposta, f'data-url="{self.url}"')
        self.assertContains(resposta, 'data-formulario="form-atendimento"')
        self.assertContains(resposta, 'data-substituir-padrao="data horario"')


class SalvarAtendimentoComEmailTests(BaseAtendimentoPorEmail):
    def test_salvar_registra_o_email_no_historico(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        resposta = self.salvar(email_origem=token)
        atendimento = Atendimento.objects.get()
        self.assertRedirects(resposta, reverse("atendimento_imprensa:editar", args=[atendimento.pk]))
        criacao = atendimento.historico.get(acao=AcaoHistorico.CRIACAO)
        self.assertEqual(
            criacao.descricao,
            "Atendimento registrado no sistema. Criado a partir do e-mail "
            "'Pedido de posicionamento - golpe do falso advogado' de Juliana Ramos (24/09/2026 14:32).",
        )
        self.assertFalse((Path(self.pasta) / "preencher-por-email" / f"{token}.bin").exists())
        duplicados = self.ler_eml().json()["duplicados"]
        self.assertEqual(duplicados[0]["url"], reverse("atendimento_imprensa:editar", args=[atendimento.pk]))

    def test_formulario_com_erro_mantem_o_vinculo(self):
        token = self.ler_eml().json()["arquivo"]["token"]
        resposta = self.salvar(email_origem=token, pedido="")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, f'name="email_origem" value="{token}"')

    def test_sem_email_o_historico_fica_como_era(self):
        self.salvar()
        self.assertEqual(Atendimento.objects.get().historico.get().descricao, "Atendimento registrado no sistema.")


class IntegranteDoUsuarioTests(SimpleTestCase):
    class Usuario:
        is_authenticated = True

        def __init__(self, nome, sobrenome="", login="x"):
            self.first_name, self.last_name, self.username = nome, sobrenome, login

        def get_full_name(self):
            return f"{self.first_name} {self.last_name}".strip()

        def get_username(self):
            return self.username

    class Integrante:
        def __init__(self, nome):
            self.nome = nome

    def test_casamentos(self):
        mariana, mariana_c, joao_p = self.Integrante("Mariana"), self.Integrante("Mariana C"), self.Integrante("João P")
        equipe = [mariana, joao_p]
        self.assertIs(integrante_do_usuario(self.Usuario("Mariana", "Costa"), equipe).valor, mariana)
        self.assertIs(integrante_do_usuario(self.Usuario("João", "Pedro Silva"), equipe).valor, joao_p)
        # O mais parecido vence; empate é dúvida.
        self.assertIs(integrante_do_usuario(self.Usuario("Mariana", "Costa"), [mariana, mariana_c]).valor, mariana_c)
        self.assertIsNone(integrante_do_usuario(self.Usuario("Mariana", "Costa"), [mariana, self.Integrante("mariana")]))
        self.assertIsNone(integrante_do_usuario(self.Usuario("Ana", "Paula"), equipe))
        # Sem nome no cadastro do usuário, o login "joao.pedro" serve.
        self.assertIs(integrante_do_usuario(self.Usuario("", "", "joao.pedro"), equipe).valor, joao_p)
        self.assertIsNone(integrante_do_usuario(None, equipe))


class QuemPedeEVeiculoTests(TestCase):
    """Jornalista, veículo e contato: apresentação, produção pelo repórter, domínio."""

    @classmethod
    def setUpTestData(cls):
        cls.tv = Veiculo.objects.create(nome="TV Paraná Sul")
        cls.diario = Veiculo.objects.create(nome="Jornal Diário do Oeste")

    @staticmethod
    def ler(texto=None, *, remetente="Ana Souza <ana.souza@gmail.com>", corpo="", assunto="Pedido"):
        from core.leitura.mensagem import ler_mensagem, ler_texto_colado

        from .preenchimento import sugestoes

        if texto is not None:
            return sugestoes(ler_texto_colado(texto))
        mensagem = EmailMessage()
        mensagem["Subject"] = assunto
        mensagem["From"] = remetente
        mensagem["To"] = "imprensa@pc.pr.gov.br"
        mensagem["Date"] = "Thu, 24 Sep 2026 14:32:00 -0300"
        mensagem.set_content(corpo)
        return sugestoes(ler_mensagem("pedido.eml", mensagem.as_bytes()))

    def test_apresentacao_vence_o_nome_do_contato_do_whatsapp(self):
        s = self.ler("[24/09/2026 08:44] Juliano Gazeta: Juliano Ferraz aqui, TV Paraná Sul\n"
                     "[24/09/2026 08:45] Juliano Gazeta: consegue os dados de furtos?")
        self.assertEqual(s["jornalista"].valor, "Juliano Ferraz")
        self.assertEqual(s["veiculo"].valor, self.tv)

    def test_producao_em_nome_do_reporter(self):
        s = self.ler(remetente="Produção TV <producao@tvparanasul.com.br>", corpo=(
            "Em nome da repórter Luana Brandt, solicitamos entrevista com o delegado.\n"
            "Contato direto da Luana: (41) 99901-2230.\n\nRoberta Kist\nProdutora - TV Paraná Sul\n(41) 3025-7700\n"))
        self.assertEqual(s["jornalista"].valor, "Luana Brandt")
        self.assertIn("99901-2230", s["contato"].valor)
        self.assertNotIn("producao@", s["contato"].valor)

    def test_veiculo_citado_como_fonte_nao_e_o_veiculo(self):
        s = self.ler(remetente="Eduardo Lima <eduardo@exemplo.com.br>", corpo=(
            "A matéria da TV Paraná Sul de ontem afirmou que o inquérito foi arquivado. Confirmam?\n\n"
            "Eduardo Lima\nDiário do Oeste\n"))
        self.assertEqual(s["veiculo"].valor, self.diario)

    def test_veiculo_pelo_nome_colado_no_dominio(self):
        s = self.ler(remetente="Everson M <everson@tvparanasul.com.br>", corpo="Aguardo a entrevista.\n\nEverson\n")
        self.assertEqual(s["veiculo"].valor, self.tv)

    def test_whatsapp_de_numero_sem_nome(self):
        s = self.ler("[24/09/2026 08:44] +55 41 99734-5521: Boa tarde, sou o Henrique Sato, da Rádio Nova FM\n")
        self.assertEqual(s["jornalista"].valor, "Henrique Sato")
        self.assertIn("99734-5521", s["contato"].valor)
        self.assertEqual(s["veiculo_novo"].valor, "Rádio Nova FM")
        self.assertNotIn("veiculo", s)
