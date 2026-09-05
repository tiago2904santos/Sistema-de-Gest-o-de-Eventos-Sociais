import datetime as dt
import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Modulo, Setor
from accounts.modulos import usuario_tem_modulo
from core.planilhas import (
    canonizar_unidade,
    chave_compacta,
    como_data,
    limpa,
    parse_hora,
    sim_nao,
)
from solicitacoes.permissions import GRUPO_ADMINISTRADOR

from .forms import PublicacaoForm
from .models import Publicacao, Responsavel, StatusPublicacao, Unidade, formatar_duracao
from .permissions import CODIGO_MODULO

User = get_user_model()


class BasePublicacoesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.setor_ascom = Setor.objects.get(nome="ASCOM")
        cls.modulo = Modulo.objects.get(codigo=CODIGO_MODULO)

        cls.ascom = User.objects.create_user("ascom", password="x")
        cls.ascom.setores.add(cls.setor_ascom)
        cls.sem_modulo = User.objects.create_user("comum", password="x")
        cls.superusuario = User.objects.create_superuser("root", password="x")
        cls.admin_modulo = User.objects.create_user("admin-pub", password="x")
        cls.admin_modulo.setores.add(cls.setor_ascom)
        grupo_admin, _ = Group.objects.get_or_create(name=GRUPO_ADMINISTRADOR)
        cls.admin_modulo.groups.add(grupo_admin)

        cls.manoela = Responsavel.objects.create(nome="Manoela")
        cls.gabriela = Responsavel.objects.create(nome="Gabriela")
        cls.dp = Unidade.objects.create(nome="DP Colombo")

    def criar_pauta(self, **kwargs):
        dados = {
            "data": dt.date(2026, 8, 10),
            "jornalista": self.manoela,
            "unidade": self.dp,
            "titulo": "PCPR prende homem por tráfico em Colombo",
            "status": StatusPublicacao.PUBLICADA,
            "data_publicacao": dt.date(2026, 8, 10),
            "criado_por": self.ascom,
        }
        dados.update(kwargs)
        return Publicacao.objects.create(**dados)


class AcessoTests(BasePublicacoesTestCase):
    def test_seed_criou_modulo_e_setor(self):
        self.assertTrue(self.modulo.setores.filter(pk=self.setor_ascom.pk).exists())
        self.assertTrue(usuario_tem_modulo(self.ascom, CODIGO_MODULO))

    def test_usuario_ascom_acessa_as_telas(self):
        self.client.force_login(self.ascom)
        for nome in ("publicacoes:painel", "publicacoes:lista", "publicacoes:nova"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200, nome)

    def test_usuario_sem_modulo_recebe_403(self):
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.client.get(reverse("publicacoes:lista")).status_code, 403)

    def test_anonimo_redireciona_para_login(self):
        resposta = self.client.get(reverse("publicacoes:lista"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])

    def test_cadastros_exigem_administrador(self):
        self.client.force_login(self.ascom)
        self.assertEqual(
            self.client.get(reverse("publicacoes:cadastro_lista", args=["equipe"])).status_code,
            403,
        )
        self.client.force_login(self.admin_modulo)
        self.assertEqual(
            self.client.get(reverse("publicacoes:cadastro_lista", args=["equipe"])).status_code,
            200,
        )

    def test_portal_mostra_modulo_conforme_acesso(self):
        self.client.force_login(self.ascom)
        self.assertContains(self.client.get(reverse("core:home")), reverse("publicacoes:painel"))
        self.client.force_login(self.sem_modulo)
        self.assertNotContains(self.client.get(reverse("core:home")), reverse("publicacoes:painel"))

    def test_navbar_contextual_so_mostra_o_modulo(self):
        self.client.force_login(self.ascom)
        resposta = self.client.get(reverse("publicacoes:painel"))
        self.assertContains(resposta, f'href="{reverse("publicacoes:lista")}"')
        self.assertNotContains(resposta, f'href="{reverse("solicitacoes:lista")}"')


class ModeloTests(BasePublicacoesTestCase):
    def test_publicada_exige_data_de_publicacao(self):
        pauta = Publicacao(
            data=dt.date(2026, 8, 10), jornalista=self.manoela, unidade=self.dp,
            titulo="x", status=StatusPublicacao.PUBLICADA,
        )
        with self.assertRaises(ValidationError) as ctx:
            pauta.full_clean()
        self.assertIn("data_publicacao", ctx.exception.message_dict)

    def test_publicacao_nao_pode_ser_anterior_a_pauta(self):
        pauta = Publicacao(
            data=dt.date(2026, 8, 10), jornalista=self.manoela, unidade=self.dp,
            titulo="x", status=StatusPublicacao.PUBLICADA,
            data_publicacao=dt.date(2026, 8, 9),
        )
        with self.assertRaises(ValidationError):
            pauta.full_clean()

    def test_tempo_ate_publicacao(self):
        pauta = self.criar_pauta(
            inicio_pauta=dt.time(15, 30),
            data_publicacao=dt.date(2026, 8, 11),
            horario_publicacao=dt.time(9, 0),
        )
        self.assertEqual(pauta.tempo_ate_publicacao, dt.timedelta(hours=17, minutes=30))
        self.assertEqual(pauta.tempo_ate_publicacao_display, "17h30")
        self.assertEqual(formatar_duracao(dt.timedelta(days=2, hours=3)), "2d 3h")
        self.assertEqual(self.criar_pauta().tempo_ate_publicacao, None)


class FormularioTests(BasePublicacoesTestCase):
    def dados(self, **extra):
        dados = {
            "data": "2026-08-10",
            "jornalista": str(self.manoela.pk),
            "unidade": str(self.dp.pk),
            "titulo": "  PCPR prende   homem em Colombo ",
            "status": StatusPublicacao.PENDENTE,
            "inicio_pauta": "17h03",
        }
        dados.update(extra)
        return dados

    def test_horario_na_grafia_da_planilha(self):
        form = PublicacaoForm(self.dados())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["inicio_pauta"], dt.time(17, 3))
        self.assertEqual(form.cleaned_data["titulo"], "PCPR prende homem em Colombo")

    def test_horario_invalido(self):
        form = PublicacaoForm(self.dados(inicio_pauta="25h99"))
        self.assertFalse(form.is_valid())
        self.assertIn("inicio_pauta", form.errors)

    def test_unidade_nova_cria_cadastro(self):
        form = PublicacaoForm(self.dados(unidade="", unidade_nova="DP Nova Londrina"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["unidade"].nome, "DP Nova Londrina")
        self.assertTrue(Unidade.objects.filter(nome="DP Nova Londrina").exists())

    def test_sem_unidade_e_sem_nova_falha(self):
        form = PublicacaoForm(self.dados(unidade=""))
        self.assertFalse(form.is_valid())
        self.assertIn("unidade", form.errors)

    def test_publicada_sem_data_falha_no_form(self):
        form = PublicacaoForm(self.dados(status=StatusPublicacao.PUBLICADA))
        self.assertFalse(form.is_valid())
        self.assertIn("data_publicacao", form.errors)

    def test_sim_nao(self):
        form = PublicacaoForm(self.dados(bitly_grupos="1", enviado_sesp="0", publicado_aen=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIs(form.cleaned_data["bitly_grupos"], True)
        self.assertIs(form.cleaned_data["enviado_sesp"], False)
        self.assertIsNone(form.cleaned_data["publicado_aen"])


class ViewsTests(BasePublicacoesTestCase):
    def setUp(self):
        self.client.force_login(self.ascom)

    def test_criacao_pela_view(self):
        resposta = self.client.post(
            reverse("publicacoes:nova"),
            {
                "data": "2026-08-10",
                "jornalista": self.manoela.pk,
                "unidade": self.dp.pk,
                "titulo": "Nova pauta",
                "status": StatusPublicacao.PENDENTE,
                "inicio_pauta": "9h",
            },
        )
        pauta = Publicacao.objects.get(titulo="Nova pauta")
        self.assertRedirects(resposta, reverse("publicacoes:detalhe", args=[pauta.pk]))
        self.assertEqual(pauta.criado_por, self.ascom)
        self.assertEqual(pauta.inicio_pauta, dt.time(9, 0))

    def test_edicao_pela_view(self):
        pauta = self.criar_pauta(status=StatusPublicacao.PENDENTE, data_publicacao=None)
        resposta = self.client.post(
            reverse("publicacoes:editar", args=[pauta.pk]),
            {
                "data": "2026-08-10",
                "jornalista": self.manoela.pk,
                "unidade": self.dp.pk,
                "titulo": pauta.titulo,
                "status": StatusPublicacao.PUBLICADA,
                "data_publicacao": "2026-08-10",
                "horario_publicacao": "16:20",
                "revisao": self.gabriela.pk,
                "enviado_sesp": "1",
                "link_site": "https://www.policiacivil.pr.gov.br/Noticia/x",
            },
        )
        self.assertRedirects(resposta, reverse("publicacoes:detalhe", args=[pauta.pk]))
        pauta.refresh_from_db()
        self.assertEqual(pauta.status, StatusPublicacao.PUBLICADA)
        self.assertEqual(pauta.horario_publicacao, dt.time(16, 20))
        self.assertEqual(pauta.revisao, self.gabriela)
        self.assertIs(pauta.enviado_sesp, True)

    def test_erro_de_validacao_volta_ao_formulario(self):
        resposta = self.client.post(
            reverse("publicacoes:nova"),
            {"data": "2026-08-10", "jornalista": self.manoela.pk, "titulo": "", "status": "PENDENTE"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Não foi possível salvar a pauta")

    def test_listagem_filtros_e_filas(self):
        self.criar_pauta(titulo="Pauta publicada")
        self.criar_pauta(
            titulo="Pauta pendente", status=StatusPublicacao.PENDENTE,
            data_publicacao=None, jornalista=self.gabriela,
        )
        resposta = self.client.get(reverse("publicacoes:lista"), {"fila": "pendentes"})
        self.assertContains(resposta, "Pauta pendente")
        self.assertNotContains(resposta, "Pauta publicada")
        resposta = self.client.get(reverse("publicacoes:lista"), {"jornalista": self.gabriela.pk})
        self.assertContains(resposta, "Pauta pendente")
        self.assertNotContains(resposta, "Pauta publicada")
        resposta = self.client.get(reverse("publicacoes:lista"), {"q": "publicada"})
        self.assertContains(resposta, "Pauta publicada")
        self.assertNotContains(resposta, "Pauta pendente")
        resposta = self.client.get(
            reverse("publicacoes:lista"), {"inicio": "2026-09-01"}
        )
        self.assertContains(resposta, "Nenhuma pauta corresponde")

    def test_ordenacao_segura(self):
        self.criar_pauta()
        resposta = self.client.get(reverse("publicacoes:lista"), {"ordem": "inexistente"})
        self.assertEqual(resposta.status_code, 200)
        resposta = self.client.get(reverse("publicacoes:lista"), {"ordem": "-titulo"})
        self.assertEqual(resposta.status_code, 200)

    def test_exportacao_csv(self):
        self.criar_pauta(titulo="Pauta exportada", enviado_sesp=True)
        resposta = self.client.get(reverse("publicacoes:exportar"))
        self.assertEqual(resposta["Content-Type"], "text/csv; charset=utf-8")
        corpo = resposta.content.decode("utf-8")
        self.assertIn("Pauta exportada", corpo)
        self.assertIn("Publicada", corpo)

    def test_detalhe_e_painel(self):
        pauta = self.criar_pauta(inicio_pauta=dt.time(10, 0), horario_publicacao=dt.time(12, 30))
        resposta = self.client.get(reverse("publicacoes:detalhe", args=[pauta.pk]))
        self.assertContains(resposta, pauta.titulo)
        self.assertContains(resposta, "2h30")
        self.assertEqual(self.client.get(reverse("publicacoes:painel")).status_code, 200)

    def test_cadastro_pela_interface(self):
        self.client.force_login(self.admin_modulo)
        resposta = self.client.post(
            reverse("publicacoes:cadastro_novo", args=["unidades"]),
            {"nome": "DHPP", "ativo": "on"},
        )
        self.assertRedirects(resposta, reverse("publicacoes:cadastro_lista", args=["unidades"]))
        unidade = Unidade.objects.get(nome="DHPP")
        self.client.post(reverse("publicacoes:cadastro_alternar", args=["unidades", unidade.pk]))
        unidade.refresh_from_db()
        self.assertFalse(unidade.ativo)
        self.assertEqual(
            self.client.get(reverse("publicacoes:cadastro_lista", args=["outro"])).status_code,
            404,
        )


class PlanilhasTests(TestCase):
    def test_parse_hora(self):
        self.assertEqual(parse_hora("17h03"), dt.time(17, 3))
        self.assertEqual(parse_hora("16h"), dt.time(16, 0))
        self.assertEqual(parse_hora("9:15"), dt.time(9, 15))
        self.assertEqual(parse_hora("17:03:00"), dt.time(17, 3))
        self.assertEqual(parse_hora(dt.time(8, 54, 30)), dt.time(8, 54))
        self.assertIsNone(parse_hora("-"))
        self.assertIsNone(parse_hora("17h29\n\n09h39"))
        self.assertIsNone(parse_hora("25h"))

    def test_sim_nao_e_datas(self):
        self.assertIs(sim_nao("SIM"), True)
        self.assertIs(sim_nao("não"), False)
        self.assertIsNone(sim_nao("-"))
        self.assertIsNone(sim_nao("GRUPOS"))
        self.assertEqual(como_data("21/08/26"), dt.date(2026, 8, 21))
        self.assertIsNone(como_data("21//08/26"))
        self.assertIsNone(como_data("31/09/26"))

    def test_canonizar_unidade_e_chave_compacta(self):
        self.assertEqual(canonizar_unidade("10DP"), "10ª DP")
        self.assertEqual(canonizar_unidade("10 DP"), "10ª DP")
        self.assertEqual(canonizar_unidade("13ª SDP Ponta \nGrossa"), "13ª SDP Ponta Grossa")
        self.assertEqual(canonizar_unidade("DP Colombo"), "DP Colombo")
        self.assertEqual(chave_compacta("Band News"), chave_compacta("BandNews"))
        self.assertEqual(limpa("DP São Mateus\ndo Sul "), "DP São Mateus do Sul")


def _planilha_publicacoes(caminho):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Agosto"
    ws.append(
        [
            "Data", "Jornalista\nResponsável", "Unidade responsável", "Fonte da pauta",
            "Início da pauta", "Título da Pauta", "Status da Pauta", "Andamento da pauta",
            "Colocada para edição", "Data de Publicação ", "Revisão", "Galeria de Fotos",
            "Horário que foi publicada", "Bitly nos grupos", "Enviado p/ Sesp?",
            "Publicado na AEN?", "Link da Publicação Site PCPR", "Link da Publicação AEN",
        ]
    )
    ws.append(
        [
            dt.datetime(2026, 8, 10), "Manoela", "DP Colombo", "Superi Marcos", "15h16",
            "PCPR prende homem em Colombo", "OK", None, "16h13", dt.datetime(2026, 8, 10),
            "Gabriela", "Manu", "17h32", "SIM", "NÃO", None,
            "https://www.policiacivil.pr.gov.br/Noticia/PCPR-prende-homem-em-Colombo", None,
        ]
    )
    ws.append(
        [
            dt.datetime(2026, 8, 11), "Kevin/Gabriela", "10DP", "-", "-",
            "PCPR divulga balanço", "OK", "tem sonora", "-", dt.datetime(2026, 8, 11),
            "JM", "Nati", "-", "SIM", "SIM",
            "https://www.aen.pr.gov.br/Noticia/balanco", None,
            "https://www.policiacivil.pr.gov.br/Noticia/balanco",
        ]
    )
    ws.append(
        [
            dt.datetime(2026, 8, 12), "Nati", "10 DP", "Dr Fulano", "9h",
            "Pauta cancelada", "CANCELADA", None, None, None, "-", "-", None, "-", "-", None, None, None,
        ]
    )
    ws.append([None] * 18)
    wb.create_sheet("Setembro").append(["Data", "Jornalista", "Unidade", "x", "x", "Título da Pauta"])
    wb.save(caminho)


class ImportacaoTests(BasePublicacoesTestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.arquivo = Path(self.pasta.name) / "publicacoes.xlsx"
        _planilha_publicacoes(self.arquivo)

    def tearDown(self):
        self.pasta.cleanup()

    def _importar(self, *extra):
        saida = io.StringIO()
        call_command("importar_publicacoes", str(self.arquivo), "--usuario", "ascom", *extra, stdout=saida)
        return saida.getvalue()

    def test_importa_linhas_e_cadastros(self):
        saida = self._importar()
        self.assertIn("3 criadas", saida)
        self.assertEqual(Publicacao.objects.count(), 3)

        colombo = Publicacao.objects.get(titulo="PCPR prende homem em Colombo")
        self.assertEqual(colombo.status, StatusPublicacao.PUBLICADA)
        self.assertEqual(colombo.inicio_pauta, dt.time(15, 16))
        self.assertEqual(colombo.horario_publicacao, dt.time(17, 32))
        self.assertEqual(colombo.galeria_fotos.nome, "Manoela")  # "Manu" unificado
        self.assertIs(colombo.bitly_grupos, True)
        self.assertIs(colombo.enviado_sesp, False)
        self.assertIsNone(colombo.publicado_aen)
        self.assertTrue(colombo.link_site.startswith("https://www.policiacivil"))

        balanco = Publicacao.objects.get(titulo="PCPR divulga balanço")
        self.assertEqual(balanco.jornalista.nome, "Kevin")
        self.assertIn("Kevin/Gabriela", balanco.andamento)
        self.assertIs(balanco.publicado_aen, True)
        self.assertEqual(balanco.link_aen, "https://www.aen.pr.gov.br/Noticia/balanco")
        self.assertEqual(balanco.link_site, "https://www.policiacivil.pr.gov.br/Noticia/balanco")
        self.assertIsNone(balanco.inicio_pauta)

        cancelada = Publicacao.objects.get(titulo="Pauta cancelada")
        self.assertEqual(cancelada.status, StatusPublicacao.CANCELADA)
        self.assertIsNone(cancelada.revisao)
        # "10DP" e "10 DP" são a mesma unidade.
        self.assertEqual(Unidade.objects.filter(nome="10ª DP").count(), 1)
        self.assertEqual(balanco.unidade, cancelada.unidade)
        self.assertEqual(colombo.criado_por, self.ascom)

    def test_importacao_idempotente(self):
        self._importar()
        saida = self._importar()
        self.assertIn("0 criadas", saida)
        self.assertIn("3 atualizadas", saida)
        self.assertEqual(Publicacao.objects.count(), 3)

    def test_dry_run_nao_persiste(self):
        saida = self._importar("--dry-run")
        self.assertIn("[dry-run]", saida)
        self.assertEqual(Publicacao.objects.count(), 0)
