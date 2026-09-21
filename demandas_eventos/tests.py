import tempfile
from datetime import date, datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from accounts.models import Modulo, Setor

from .forms import DemandaEventoForm
from .models import (
    DemandaEvento,
    Palestrante,
    RespostaPadrao,
    StatusDemanda,
    Tema,
    TipoEventoPalestra,
)
from .permissions import CODIGO_MODULO

User = get_user_model()


class BaseDemandasTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.modulo = Modulo.objects.get(codigo=CODIGO_MODULO)
        cls.ascom = Setor.objects.get(sigla="ASCOM")
        cls.usuario = User.objects.create_user("ascom", password="x")
        cls.usuario.setores.add(cls.ascom)
        cls.outro_setor = Setor.objects.create(sigla="ASCOM-2", nome="Outra equipe ASCOM")
        cls.outro_setor.modulos.add(cls.modulo)
        cls.outro = User.objects.create_user("outra_ascom", password="x")
        cls.outro.setores.add(cls.outro_setor)
        cls.sem_modulo = User.objects.create_user("iipr", password="x")
        cls.sem_modulo.setores.add(Setor.objects.create(sigla="IIPR", nome="Instituto de Identificação"))
        cls.superusuario = User.objects.create_superuser("root_demandas", password="x")
        cls.tema = Tema.objects.create(nome="Crimes virtuais")

    def criar_demanda(self, setor=None, **kwargs):
        dados = {
            "data_solicitacao": date(2026, 8, 1),
            "evento": TipoEventoPalestra.PALESTRA,
            "tema": self.tema,
            "solicitante": "Escola Municipal",
            "status": StatusDemanda.PENDENTE,
            "criado_por": self.usuario,
        }
        dados.update(kwargs)
        demanda = DemandaEvento.objects.create(**dados)
        demanda.setores.add(setor or self.ascom)
        return demanda


class AcessoDemandasTests(BaseDemandasTestCase):
    def test_modulo_bloqueia_url_direta(self):
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.client.get(reverse("demandas_eventos:dashboard")).status_code, 403)

    def test_portal_mostra_modulo_conforme_acesso(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("core:home"))
        self.assertContains(resposta, reverse("demandas_eventos:dashboard"))
        self.client.force_login(self.sem_modulo)
        resposta = self.client.get(reverse("core:home"))
        self.assertNotContains(resposta, reverse("demandas_eventos:dashboard"))

    def test_navbar_contextual_dentro_do_modulo(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("demandas_eventos:dashboard"))
        self.assertContains(resposta, f'href="{reverse("demandas_eventos:lista")}"')
        self.assertContains(resposta, "Palestras")
        self.assertNotContains(resposta, f'href="{reverse("coffee_break:painel")}"')

    def test_isolamento_por_setor_e_superusuario_global(self):
        demanda = self.criar_demanda()
        self.client.force_login(self.outro)
        self.assertNotContains(self.client.get(reverse("demandas_eventos:lista")), "Escola Municipal")
        self.assertEqual(self.client.get(reverse("demandas_eventos:editar", args=[demanda.pk])).status_code, 404)
        self.client.force_login(self.superusuario)
        self.assertEqual(self.client.get(reverse("demandas_eventos:editar", args=[demanda.pk])).status_code, 200)


class FormulariosViewsTests(BaseDemandasTestCase):
    def dados_post(self, **extra):
        dados = {
            "evento": TipoEventoPalestra.PALESTRA,
            "data_inicio_evento": "2026-09-10",
            "data_fim_evento": "2026-09-11",
            "periodo_evento_texto": "14h às 16h",
            "status": StatusDemanda.PENDENTE,
            "solicitante": "Colégio Estadual",
            "contato": "colegio@example.org",
            "data_solicitacao": "2026-08-20",
            "canal_solicitacao": "E-MAIL",
            "quantidade_publico": "120",
            "tema": self.tema.pk,
            "servidor": "Dra. Teste",
        }
        dados.update(extra)
        return dados

    def test_formulario_tem_um_campo_por_coluna_da_planilha(self):
        rotulos = {campo.label.lower() for campo in DemandaEventoForm(usuario=self.usuario).fields.values() if campo.label}
        for coluna in (
            "município", "data do evento", "hora (período)", "evento", "status da demanda",
            "andamento", "informações prévias", "solicitante", "contato", "data da solicitação",
            "foi solicitado via", "descrição", "quantidade de público", "assunto e-mail",
            "pedido/contato", "tema", "servidor",
        ):
            self.assertIn(coluna, rotulos)
        self.assertNotIn("setores", DemandaEventoForm(usuario=self.usuario).fields)

    def test_form_rejeita_periodo_invertido(self):
        form = DemandaEventoForm(self.dados_post(data_fim_evento="2026-09-01"), usuario=self.usuario)
        self.assertFalse(form.is_valid())
        self.assertIn("data_fim_evento", form.errors)

    def test_solicitante_com_texto_legado_extenso_e_preservado(self):
        self.assertEqual(DemandaEvento._meta.get_field("solicitante").max_length, 1000)
        demanda = self.criar_demanda(solicitante="A" * 500)
        self.assertEqual(len(demanda.solicitante), 500)

    def test_cria_edita_e_registra_status_no_historico(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(reverse("demandas_eventos:nova"), self.dados_post())
        demanda = DemandaEvento.objects.get(solicitante="Colégio Estadual")
        self.assertRedirects(resposta, reverse("demandas_eventos:editar", args=[demanda.pk]))
        # A linha fica com o setor de quem registrou, sem campo na tela.
        self.assertEqual(list(demanda.setores.all()), [self.ascom])
        self.assertEqual(demanda.quantidade_publico, 120)
        resposta = self.client.get(reverse("demandas_eventos:editar", args=[demanda.pk]))
        self.assertContains(resposta, "Colégio Estadual")
        self.assertContains(resposta, "Editar palestra")
        self.assertContains(resposta, "Status da demanda")
        self.assertContains(resposta, "Histórico")
        self.assertNotContains(resposta, "<aside")
        self.assertEqual(demanda.historico.count(), 1)

        dados = self.dados_post(status=StatusDemanda.ATENDIDA, andamento="Palestra realizada")
        dados["versao"] = resposta.context["valores"]["versao"]
        self.client.post(reverse("demandas_eventos:editar", args=[demanda.pk]), dados)
        demanda.refresh_from_db()
        self.assertEqual(demanda.status, StatusDemanda.ATENDIDA)
        acoes = list(demanda.historico.values_list("acao", flat=True))
        self.assertEqual(acoes, ["CRIACAO", "TRANSICAO", "ATUALIZACAO"])
        # Como na planilha, a linha atendida continua editável.
        self.assertEqual(
            self.client.get(reverse("demandas_eventos:editar", args=[demanda.pk])).status_code, 200
        )

    def test_edicao_concorrente_e_rejeitada(self):
        demanda = self.criar_demanda()
        versao_antiga = str(int(demanda.atualizado_em.timestamp() * 1_000_000))
        demanda.andamento = "Alteração concorrente"
        demanda.save(update_fields=["andamento", "atualizado_em"])
        self.client.force_login(self.usuario)
        resposta = self.client.post(
            reverse("demandas_eventos:editar", args=[demanda.pk]), self.dados_post(versao=versao_antiga)
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "alterado por outra pessoa")

    def test_listagem_filtra_status_evento_e_busca(self):
        self.criar_demanda(solicitante="Demanda visível", status=StatusDemanda.PENDENTE)
        self.criar_demanda(solicitante="Demanda concluída", status=StatusDemanda.ATENDIDA)
        self.criar_demanda(solicitante="Ação no bairro", evento=TipoEventoPalestra.PCPR_NA_COMUNIDADE)
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("demandas_eventos:lista"), {"status": StatusDemanda.ATENDIDA})
        self.assertContains(resposta, "Demanda concluída")
        self.assertNotContains(resposta, "Demanda visível")
        resposta = self.client.get(reverse("demandas_eventos:lista"), {"evento": TipoEventoPalestra.PCPR_NA_COMUNIDADE})
        self.assertContains(resposta, "Ação no bairro")
        self.assertNotContains(resposta, "Demanda visível")
        resposta = self.client.get(reverse("demandas_eventos:lista"), {"q": "visível"})
        self.assertContains(resposta, "Demanda visível")

    def test_datas_invalidas_nos_filtros_nao_geram_erro(self):
        self.criar_demanda(solicitante="Demanda visível")
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("demandas_eventos:lista"), {"inicio": "31-02-2026", "fim": "invalida"})
        self.assertEqual(resposta.status_code, 200)
        resposta = self.client.get(reverse("demandas_eventos:exportar"), {"inicio": "invalida"})
        self.assertEqual(resposta.status_code, 200)

    def test_exportacao_sai_nas_colunas_da_planilha_e_respeita_recorte(self):
        self.criar_demanda(solicitante="Demanda exportável", data_inicio_evento=date(2026, 9, 3))
        self.criar_demanda(setor=self.outro_setor, solicitante="Demanda de outro setor")
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("demandas_eventos:exportar"))
        linhas = resposta.content.decode("utf-8-sig").splitlines()
        self.assertTrue(linhas[0].startswith("MÊS;MUNICIPIO;DATA DO EVENTO E HORA (PERÍODO);EVENTO;STATUS DA DEMANDA"))
        self.assertIn("SETEMBRO;", linhas[1])
        self.assertIn("Demanda exportável", linhas[1])
        self.assertNotIn("Demanda de outro setor", "\n".join(linhas))

    def test_cadastro_de_resposta_padrao(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(
            reverse("demandas_eventos:cadastro_novo", args=["respostas"]),
            {"tipo": "Pedido incompleto", "mensagem": "Solicite os dados faltantes."},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(RespostaPadrao.objects.filter(tipo="Pedido incompleto").exists())


class CadastrosEmModalTests(BaseDemandasTestCase):
    MODAL = {"HTTP_X_CADASTRO_MODAL": "1"}

    def test_lista_abre_criar_e_editar_em_modal(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("demandas_eventos:cadastro_lista", args=["temas"]))
        self.assertContains(resposta, "data-cadastro-dialog")
        self.assertContains(resposta, 'href="%s" data-cadastro-modal' % reverse("demandas_eventos:cadastro_novo", args=["temas"]))
        # Sem JavaScript, o endereço do formulário leva à lista com o modal aberto.
        resposta = self.client.get(reverse("demandas_eventos:cadastro_editar", args=["temas", self.tema.pk]))
        self.assertRedirects(resposta, reverse("demandas_eventos:cadastro_lista", args=["temas"]) + f"?editar={self.tema.pk}")
        resposta = self.client.get(resposta["Location"])
        self.assertContains(resposta, "data-cadastro-inicial")
        self.assertContains(resposta, "Editar tema")

    def test_modal_devolve_o_trecho_e_salva_com_json(self):
        self.client.force_login(self.usuario)
        url = reverse("demandas_eventos:cadastro_novo", args=["palestrantes"])
        resposta = self.client.get(url, **self.MODAL)
        self.assertTemplateUsed(resposta, "pages/demandas_eventos/_modal_cadastro.html")
        self.assertContains(resposta, "Tema de abordagem")
        self.assertNotContains(resposta, "<html")
        resposta = self.client.post(url, {"nome": ""}, **self.MODAL)
        self.assertContains(resposta, "Não foi possível salvar palestrante")
        resposta = self.client.post(
            url, {"nome": "Dra. Nova", "lotacao": "NUCIBER", "tema_abordagem": "Crimes digitais"}, **self.MODAL
        )
        self.assertEqual(resposta.json(), {"ok": True})
        self.assertEqual(Palestrante.objects.get(nome="Dra. Nova").tema_abordagem, "Crimes digitais")

    def test_tema_em_uso_nao_e_excluido(self):
        self.criar_demanda()
        self.client.force_login(self.usuario)
        self.client.post(reverse("demandas_eventos:cadastro_excluir", args=["temas", self.tema.pk]))
        self.assertTrue(Tema.objects.filter(pk=self.tema.pk).exists())
        livre = Tema.objects.create(nome="Tema sem uso")
        self.client.post(reverse("demandas_eventos:cadastro_excluir", args=["temas", livre.pk]))
        self.assertFalse(Tema.objects.filter(pk=livre.pk).exists())


class ImportacaoPlanilhaTests(BaseDemandasTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.arquivo = Path(self.tmp.name) / "ascom.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "2026"
        ws.append([
            "MÊS", "MUNICIPIO", "DATA DO EVENTO E HORA (PERÍODO)", "EVENTO",
            "STATUS DA DEMANDA", "ANDAMENTO", "INFORMAÇÕES PRÉVIAS", "SOLICITANTE",
            "CONTATO", "DATA DA SOLICITAÇÃO", "FOI SOLICITADO VIA:", "DESCRIÇÃO",
            "QUANTIDADE DE PÚBLICO", "ASSUNTO E-MAIL", "PEDIDO/CONTATO",
        ])
        ws.append([
            "AGOSTO", "Curitiba", "10 e 11/09 14h", "PALESTRA", "EVENTO AGENDADO",
            "Confirmado", "Levar projetor", "Escola Teste", "41 99999-0000",
            datetime(2026, 8, 20), "E-MAIL", "Palestra educativa", 120,
            "Solicitação de palestra", "Pedido completo",
        ])
        ws.append([
            "AGOSTO", "Curitiba", "À definir", "PCPR NA COMUNIDADE", "SOL. ATENDIDA",
            "", "", "Prefeitura Teste", "", datetime(2026, 8, 21), "WPP", "", "?",
            "", "Pedido",
        ])
        antigo = wb.create_sheet("2024")
        antigo.append([
            "Mês", "Data da Solicitação", "Tipo de Evento", "Por onde foi solicitado", "Tema",
            "Status da demanda", "Andamento", "Data do evento", "Solicitante", "Contato",
            "Município", "Pedido/Contato", "Servidor", "Unidade", "Público",
            "Breafing Palestra", "Matéria no Site", "Responsável pelo Atendimento",
        ])
        antigo.append([
            "MAIO", datetime(2024, 5, 2), "Inauguração", "E-MAIL", "Segurança", "ATENDIDA",
            "", datetime(2024, 5, 20), "Delegacia Teste", "", "Curitiba", "Pedido antigo",
            "Dr. Fulano", "NUCIBER", 80, "Briefing antigo", "https://site", "Maria",
        ])
        temas = wb.create_sheet("TEMAS")
        temas.append(["Prevenção"])
        palestrantes = wb.create_sheet("PALESTRANTES")
        palestrantes.append(["MUNICÍPIO", "DIVISÃO", "LOTAÇÃO", "SERVIDOR", "CONTATO", "E-MAIL", "TEMA DE ABORDAGEM"])
        palestrantes.append(["Curitiba", "DIC", "NUCIBER", "Dra. Teste", "41 90000-0000", "teste@pc.pr.gov.br", "Prevenção"])
        respostas = wb.create_sheet("Repostas Padrão")
        respostas.append(["TIPO", "MENSAGEM"])
        respostas.append(["Recebimento", "Demanda recebida."])
        wb.save(self.arquivo)
        wb.close()

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def test_dry_run_nao_persiste(self):
        call_command("importar_planilha_ascom", str(self.arquivo), dry_run=True)
        self.assertFalse(DemandaEvento.objects.filter(solicitante="Escola Teste").exists())

    def test_importacao_idempotente_leva_cada_coluna_ao_seu_campo(self):
        call_command("importar_planilha_ascom", str(self.arquivo))
        call_command("importar_planilha_ascom", str(self.arquivo))
        self.assertEqual(DemandaEvento.objects.filter(solicitante="Escola Teste").count(), 1)
        demanda = DemandaEvento.objects.get(solicitante="Escola Teste")
        self.assertEqual(demanda.evento, TipoEventoPalestra.PALESTRA)
        self.assertEqual(demanda.data_inicio_evento, date(2026, 9, 10))
        self.assertEqual(demanda.data_fim_evento, date(2026, 9, 11))
        self.assertEqual(demanda.periodo_evento_texto, "14h")
        self.assertEqual(demanda.status, StatusDemanda.EVENTO_AGENDADO)
        self.assertEqual(demanda.quantidade_publico, 120)
        self.assertEqual(demanda.informacoes_previas, "Levar projetor")
        self.assertEqual(demanda.historico.count(), 1)

        pcpr = DemandaEvento.objects.get(solicitante="Prefeitura Teste")
        self.assertEqual(pcpr.evento, TipoEventoPalestra.PCPR_NA_COMUNIDADE)
        self.assertEqual(pcpr.status, StatusDemanda.ATENDIDA)
        self.assertEqual(pcpr.periodo_evento_texto, "À definir")
        self.assertIsNone(pcpr.quantidade_publico)
        self.assertIn("Quantidade de público: ?", pcpr.informacoes_previas)

        self.assertEqual(Palestrante.objects.get(nome="Dra. Teste").tema_abordagem, "Prevenção")
        self.assertTrue(RespostaPadrao.objects.filter(tipo="Recebimento").exists())

    def test_so_os_temas_da_aba_temas_ficam(self):
        usado = self.criar_demanda(solicitante="Linha antiga")
        call_command("importar_planilha_ascom", str(self.arquivo))
        self.assertEqual(list(Tema.objects.values_list("nome", flat=True)), ["Prevenção"])
        usado.refresh_from_db()
        self.assertIsNone(usado.tema)
        self.assertIn("Tema: Crimes virtuais", usado.informacoes_previas)
        # O texto livre da coluna Tema não vira tema novo.
        antiga = DemandaEvento.objects.get(solicitante="Delegacia Teste")
        self.assertIsNone(antiga.tema)
        self.assertIn("Tema: Segurança", antiga.informacoes_previas)

    def test_colunas_dos_anos_anteriores_vao_para_informacoes_previas(self):
        call_command("importar_planilha_ascom", str(self.arquivo))
        antiga = DemandaEvento.objects.get(solicitante="Delegacia Teste")
        self.assertEqual(antiga.evento, TipoEventoPalestra.EVENTO)
        self.assertEqual(antiga.servidor, "Dr. Fulano")
        self.assertEqual(antiga.quantidade_publico, 80)
        for trecho in ("Tipo de evento: Inauguração", "Unidade: NUCIBER", "Briefing: Briefing antigo",
                       "Matéria no site: https://site", "Responsável pelo atendimento: Maria"):
            self.assertIn(trecho, antiga.informacoes_previas)
