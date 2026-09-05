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
from solicitacoes.permissions import GRUPO_ADMINISTRADOR

from .forms import AtendimentoForm
from .management.commands.importar_atendimentos import situacao_da_planilha
from .models import Atendimento, Responsavel, SituacaoAtendimento, Veiculo
from .permissions import CODIGO_MODULO

User = get_user_model()


class BaseAtendimentoTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.setor_ascom = Setor.objects.get(nome="ASCOM")
        cls.modulo = Modulo.objects.get(codigo=CODIGO_MODULO)

        cls.ascom = User.objects.create_user("ascom", password="x")
        cls.ascom.setores.add(cls.setor_ascom)
        cls.sem_modulo = User.objects.create_user("comum", password="x")
        cls.superusuario = User.objects.create_superuser("root", password="x")
        cls.admin_modulo = User.objects.create_user("admin-imp", password="x")
        cls.admin_modulo.setores.add(cls.setor_ascom)
        grupo_admin, _ = Group.objects.get_or_create(name=GRUPO_ADMINISTRADOR)
        cls.admin_modulo.groups.add(grupo_admin)

        cls.joao = Responsavel.objects.create(nome="João P")
        cls.mariana = Responsavel.objects.create(nome="Mariana")
        cls.ric = Veiculo.objects.create(nome="RIC")

    def criar_atendimento(self, **kwargs):
        dados = {
            "data": dt.date(2026, 8, 10),
            "horario": dt.time(9, 30),
            "jornalista": "Paola",
            "veiculo": self.ric,
            "pedido": "Informações sobre o homicídio em Colombo",
            "situacao": SituacaoAtendimento.ATENDIDO,
            "responsavel": self.joao,
            "resposta": "A PCPR informa que investiga o caso.",
            "criado_por": self.ascom,
        }
        dados.update(kwargs)
        return Atendimento.objects.create(**dados)


class AcessoTests(BaseAtendimentoTestCase):
    def test_seed_criou_modulo_e_setor(self):
        self.assertTrue(self.modulo.setores.filter(pk=self.setor_ascom.pk).exists())
        self.assertTrue(usuario_tem_modulo(self.ascom, CODIGO_MODULO))

    def test_usuario_ascom_acessa_as_telas(self):
        self.client.force_login(self.ascom)
        for nome in (
            "atendimento_imprensa:painel",
            "atendimento_imprensa:lista",
            "atendimento_imprensa:novo",
        ):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200, nome)

    def test_usuario_sem_modulo_recebe_403(self):
        self.client.force_login(self.sem_modulo)
        self.assertEqual(
            self.client.get(reverse("atendimento_imprensa:lista")).status_code, 403
        )

    def test_anonimo_redireciona_para_login(self):
        resposta = self.client.get(reverse("atendimento_imprensa:lista"))
        self.assertEqual(resposta.status_code, 302)

    def test_cadastros_exigem_administrador(self):
        url = reverse("atendimento_imprensa:cadastro_lista", args=["veiculos"])
        self.client.force_login(self.ascom)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin_modulo)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_portal_e_navbar(self):
        self.client.force_login(self.ascom)
        self.assertContains(
            self.client.get(reverse("core:home")), reverse("atendimento_imprensa:painel")
        )
        resposta = self.client.get(reverse("atendimento_imprensa:painel"))
        self.assertContains(resposta, f'href="{reverse("atendimento_imprensa:lista")}"')
        self.assertNotContains(resposta, f'href="{reverse("publicacoes:lista")}"')


class ModeloTests(BaseAtendimentoTestCase):
    def test_atendido_exige_resposta_ou_andamento(self):
        atendimento = Atendimento(
            data=dt.date(2026, 8, 10), jornalista="Paola", pedido="x",
            situacao=SituacaoAtendimento.ATENDIDO,
        )
        with self.assertRaises(ValidationError):
            atendimento.full_clean()
        atendimento.andamento = "respondido por telefone"
        atendimento.full_clean()

    def test_fontes_alinhadas(self):
        atendimento = self.criar_atendimento(
            fonte="Del Leandro\n\nDel Vanessa",
            inicio_pedido="17h29\n\n09h39",
            final_pedido="09h36",
        )
        linhas = atendimento.fontes_alinhadas
        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[0], {"fonte": "Del Leandro", "inicio": "17h29", "fim": "09h36"})
        self.assertEqual(linhas[1], {"fonte": "Del Vanessa", "inicio": "09h39", "fim": ""})
        self.assertEqual(self.criar_atendimento().fontes_alinhadas, [])

    def test_propriedades(self):
        aberto = self.criar_atendimento(situacao=SituacaoAtendimento.AGUARDANDO_FONTE)
        self.assertTrue(aberto.aberto)
        self.assertFalse(aberto.atendido)
        self.assertEqual(aberto.situacao_css, "aguardando")
        longo = self.criar_atendimento(pedido="palavra " * 40)
        self.assertTrue(longo.pedido_resumo.endswith("…"))
        self.assertLessEqual(len(longo.pedido_resumo), 90)


class FormularioTests(BaseAtendimentoTestCase):
    def dados(self, **extra):
        dados = {
            "data": "2026-08-10",
            "horario": "9h05",
            "jornalista": " Paola ",
            "veiculo": str(self.ric.pk),
            "pedido": "Informações sobre o caso",
            "situacao": SituacaoAtendimento.EM_ANDAMENTO,
        }
        dados.update(extra)
        return dados

    def test_horario_na_grafia_da_planilha(self):
        form = AtendimentoForm(self.dados())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["horario"], dt.time(9, 5))
        self.assertEqual(form.cleaned_data["jornalista"], "Paola")

    def test_veiculo_novo_cria_cadastro(self):
        form = AtendimentoForm(self.dados(veiculo="", veiculo_novo="Rádio Clube"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["veiculo"].nome, "Rádio Clube")

    def test_sem_veiculo_e_permitido(self):
        form = AtendimentoForm(self.dados(veiculo=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["veiculo"])

    def test_deadline_anterior_ao_pedido(self):
        form = AtendimentoForm(self.dados(deadline="2026-08-09"))
        self.assertFalse(form.is_valid())
        self.assertIn("deadline", form.errors)

    def test_atendido_sem_resposta(self):
        form = AtendimentoForm(self.dados(situacao=SituacaoAtendimento.ATENDIDO))
        self.assertFalse(form.is_valid())
        self.assertIn("resposta", form.errors)


class ViewsTests(BaseAtendimentoTestCase):
    def setUp(self):
        self.client.force_login(self.ascom)

    def test_criacao_pela_view(self):
        resposta = self.client.post(
            reverse("atendimento_imprensa:novo"),
            {
                "data": "2026-08-10",
                "horario": "10h",
                "jornalista": "Cristina",
                "veiculo": self.ric.pk,
                "pedido": "Entrevista sobre o caso",
                "situacao": SituacaoAtendimento.AGUARDANDO_FONTE,
                "responsavel": self.mariana.pk,
                "deadline": "2026-08-10",
            },
        )
        atendimento = Atendimento.objects.get(jornalista="Cristina")
        self.assertRedirects(
            resposta, reverse("atendimento_imprensa:detalhe", args=[atendimento.pk])
        )
        self.assertEqual(atendimento.horario, dt.time(10, 0))
        self.assertEqual(atendimento.criado_por, self.ascom)

    def test_edicao_pela_view(self):
        atendimento = self.criar_atendimento(
            situacao=SituacaoAtendimento.AGUARDANDO_FONTE, resposta=""
        )
        resposta = self.client.post(
            reverse("atendimento_imprensa:editar", args=[atendimento.pk]),
            {
                "data": "2026-08-10",
                "horario": "09:30",
                "jornalista": "Paola",
                "veiculo": self.ric.pk,
                "pedido": atendimento.pedido,
                "situacao": SituacaoAtendimento.ATENDIDO,
                "responsavel": self.joao.pk,
                "horario_resposta": "11h40",
                "responsavel_resposta": self.mariana.pk,
                "fonte": "Del Fulano",
                "inicio_pedido": "09h40",
                "final_pedido": "11h20",
                "resposta": "A PCPR informa...",
            },
        )
        self.assertRedirects(
            resposta, reverse("atendimento_imprensa:detalhe", args=[atendimento.pk])
        )
        atendimento.refresh_from_db()
        self.assertEqual(atendimento.situacao, SituacaoAtendimento.ATENDIDO)
        self.assertEqual(atendimento.horario_resposta, dt.time(11, 40))
        self.assertEqual(atendimento.responsavel_resposta, self.mariana)

    def test_listagem_filtros_e_filas(self):
        self.criar_atendimento(jornalista="Atendida Silva")
        self.criar_atendimento(
            jornalista="Pendente Souza", situacao=SituacaoAtendimento.AGUARDANDO_FONTE,
            resposta="", responsavel=self.mariana, veiculo=None,
        )
        lista = reverse("atendimento_imprensa:lista")
        resposta = self.client.get(lista, {"fila": "abertos"})
        self.assertContains(resposta, "Pendente Souza")
        self.assertNotContains(resposta, "Atendida Silva")
        resposta = self.client.get(lista, {"responsavel": self.mariana.pk})
        self.assertContains(resposta, "Pendente Souza")
        self.assertNotContains(resposta, "Atendida Silva")
        resposta = self.client.get(lista, {"veiculo": self.ric.pk})
        self.assertContains(resposta, "Atendida Silva")
        self.assertNotContains(resposta, "Pendente Souza")
        resposta = self.client.get(lista, {"q": "homicídio", "ordem": "deadline"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Atendida Silva")

    def test_exportacao_csv(self):
        self.criar_atendimento(jornalista="Exportada Lima")
        resposta = self.client.get(reverse("atendimento_imprensa:exportar"))
        corpo = resposta.content.decode("utf-8")
        self.assertIn("Exportada Lima", corpo)
        self.assertIn("Atendido", corpo)

    def test_detalhe_com_deadline_vencido_e_painel(self):
        atendimento = self.criar_atendimento(
            situacao=SituacaoAtendimento.AGUARDANDO_FONTE, resposta="",
            deadline=dt.date(2026, 8, 11),
        )
        resposta = self.client.get(
            reverse("atendimento_imprensa:detalhe", args=[atendimento.pk])
        )
        self.assertContains(resposta, "Deadline vencido")
        self.assertEqual(self.client.get(reverse("atendimento_imprensa:painel")).status_code, 200)

    def test_cadastro_pela_interface(self):
        self.client.force_login(self.admin_modulo)
        resposta = self.client.post(
            reverse("atendimento_imprensa:cadastro_novo", args=["equipe"]),
            {"nome": "Natália", "ativo": "on"},
        )
        self.assertRedirects(
            resposta, reverse("atendimento_imprensa:cadastro_lista", args=["equipe"])
        )
        self.assertTrue(Responsavel.objects.filter(nome="Natália").exists())


def _planilha_atendimentos(caminho):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Agosto"
    ws.append(
        [
            "Data", "Horário", "Jornalista", "Veículo", "Contato", "Pedido", "Situação",
            "Responsável", "Deadline/\nVeiculação", "Horário da resposta", "Responsável",
            "Fonte", "Início do pedido", "Final do pedido  ", "Andamento", "Resposta",
        ]
    )
    ws.append(
        [
            dt.datetime(2026, 8, 10), "15h52", "Paola", "RIC", "41 9225-0848",
            "Tem informações sobre o caso?", "OK", "João Pedro", dt.datetime(2026, 8, 10),
            "16h31", "João P", "Del Leandro\n\nDel Vanessa", "17h29\n\n09h39", "09h36\n\n09h32",
            "Del Leandro: está com a DPP", "A PCPR informa que investiga.",
        ]
    )
    ws.append(
        [
            dt.datetime(2026, 8, 11), "07h07", "Cristina", "Band News", "cristina@x.com",
            "Entrevista gravada?", "AGUARDANDO FONTE", "Mariana", "21//08/26", None, None,
            "Ascom DHPP", "07h20", None, None, None,
        ]
    )
    ws.append(
        [
            dt.datetime(2026, 8, 12), "08h00", "Roberto", "BandNews", None,
            "Vídeo do caso", "EM ANDAMENTO - Vídeo", "Upgrade", dt.datetime(2026, 8, 12),
            None, "12h29", None, None, None, None, None,
        ]
    )
    ws.append([None] * 16)
    wb.create_sheet("Setembro").append(["Data", "Horário", "Jornalista", "Veículo", "Contato", "Pedido"])
    wb.save(caminho)


class ImportacaoTests(BaseAtendimentoTestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.arquivo = Path(self.pasta.name) / "atendimentos.xlsx"
        _planilha_atendimentos(self.arquivo)

    def tearDown(self):
        self.pasta.cleanup()

    def _importar(self, *extra):
        saida = io.StringIO()
        call_command(
            "importar_atendimentos", str(self.arquivo), "--usuario", "ascom", *extra, stdout=saida
        )
        return saida.getvalue()

    def test_importa_linhas_e_cadastros(self):
        saida = self._importar()
        self.assertIn("3 criados", saida)
        self.assertEqual(Atendimento.objects.count(), 3)

        paola = Atendimento.objects.get(jornalista="Paola")
        self.assertEqual(paola.situacao, SituacaoAtendimento.ATENDIDO)
        self.assertEqual(paola.horario, dt.time(15, 52))
        self.assertEqual(paola.horario_resposta, dt.time(16, 31))
        self.assertEqual(paola.responsavel.nome, "João P")  # "João Pedro" unificado
        self.assertEqual(paola.responsavel_resposta, paola.responsavel)
        self.assertEqual(paola.veiculo, self.ric)
        self.assertEqual(paola.deadline, dt.date(2026, 8, 10))
        self.assertEqual(len(paola.fontes_alinhadas), 2)
        self.assertEqual(paola.criado_por, self.ascom)

        cristina = Atendimento.objects.get(jornalista="Cristina")
        self.assertEqual(cristina.situacao, SituacaoAtendimento.AGUARDANDO_FONTE)
        self.assertIsNone(cristina.deadline)  # "21//08/26" ilegível
        self.assertIn("ilegível", saida)
        self.assertEqual(cristina.responsavel, self.mariana)

        roberto = Atendimento.objects.get(jornalista="Roberto")
        self.assertEqual(roberto.situacao, SituacaoAtendimento.EM_ANDAMENTO_VIDEO)
        self.assertIsNone(roberto.responsavel)  # "Upgrade" é lixo
        self.assertIsNone(roberto.responsavel_resposta)  # "12h29" é lixo
        # "Band News" e "BandNews" viram um único veículo.
        self.assertEqual(cristina.veiculo, roberto.veiculo)
        self.assertEqual(Veiculo.objects.count(), 2)

    def test_importacao_idempotente(self):
        self._importar()
        saida = self._importar()
        self.assertIn("0 criados", saida)
        self.assertIn("3 atualizados", saida)
        self.assertEqual(Atendimento.objects.count(), 3)

    def test_dry_run_nao_persiste(self):
        saida = self._importar("--dry-run")
        self.assertIn("[dry-run]", saida)
        self.assertEqual(Atendimento.objects.count(), 0)

    def test_situacao_da_planilha(self):
        self.assertEqual(situacao_da_planilha("OK"), SituacaoAtendimento.ATENDIDO)
        self.assertEqual(situacao_da_planilha("NÃO RESPONDER"), SituacaoAtendimento.NAO_RESPONDER)
        self.assertEqual(situacao_da_planilha("EM ANDAMENTO - Texto"), SituacaoAtendimento.EM_ANDAMENTO_TEXTO)
        self.assertEqual(situacao_da_planilha("PRÓXIMO MÊS"), SituacaoAtendimento.PROXIMO_MES)
        self.assertIsNone(situacao_da_planilha("qualquer coisa"))
