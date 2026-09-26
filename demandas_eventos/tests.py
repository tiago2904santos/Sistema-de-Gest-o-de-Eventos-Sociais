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
            "solicitante": "Escola Municipal",
            "status": StatusDemanda.PENDENTE,
            "criado_por": self.usuario,
        }
        dados.update(kwargs)
        demanda = DemandaEvento.objects.create(**dados)
        demanda.setores.add(setor or self.ascom)
        demanda.temas.add(self.tema)
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
            "hora_inicio": "14:00",
            "solicitante": "Colégio Estadual",
            "telefone": "41999990000",
            "email": "Colegio@Example.org",
            "data_solicitacao": "2026-08-20",
            "canal_solicitacao": "EMAIL",
            "quantidade_publico": "120",
            "temas": [self.tema.pk],
        }
        dados.update(extra)
        return dados

    def test_formulario_tem_um_campo_por_coluna_da_planilha(self):
        rotulos = {campo.label.lower() for campo in DemandaEventoForm(usuario=self.usuario).fields.values() if campo.label}
        for coluna in (
            "município", "data do evento", "horário", "evento",
            "informações prévias", "solicitante", "telefone", "e-mail", "data da solicitação",
            "foi solicitado via", "descrição", "quantidade de público", "assunto e-mail",
            "pedido/contato", "tema", "servidor", "nº do protocolo",
        ):
            self.assertIn(coluna, rotulos)
        campos = DemandaEventoForm(usuario=self.usuario).fields
        for fora in ("setores", "status", "andamento", "contato"):
            self.assertNotIn(fora, campos)

    def test_protocolo_so_quando_o_canal_e_protocolo_e_sai_com_mascara(self):
        form = DemandaEventoForm(self.dados_post(canal_solicitacao="PROTOCOLO", protocolo=""), usuario=self.usuario)
        self.assertFalse(form.is_valid())
        self.assertIn("protocolo", form.errors)
        form = DemandaEventoForm(self.dados_post(canal_solicitacao="PROTOCOLO", protocolo="251669899"), usuario=self.usuario)
        self.assertTrue(form.is_valid(), form.errors)
        demanda = form.save(criado_por=self.usuario)
        self.assertEqual(demanda.protocolo, "25.166.989-9")
        self.assertEqual(demanda.canal_display, "Protocolo Nº 25.166.989-9")
        form = DemandaEventoForm(self.dados_post(canal_solicitacao="EMAIL", protocolo="251669899"), usuario=self.usuario)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["protocolo"], "")

    def test_varios_temas_e_palestrantes(self):
        outro = Tema.objects.create(nome="Bullying e cyberbulling")
        palestrante = Palestrante.objects.create(nome="Dr. Thiago", tema_abordagem="Cyberbullying")
        form = DemandaEventoForm(
            self.dados_post(temas=[self.tema.pk, outro.pk], palestrantes=[palestrante.pk]), usuario=self.usuario
        )
        self.assertTrue(form.is_valid(), form.errors)
        demanda = form.save(criado_por=self.usuario)
        self.assertEqual(demanda.temas.count(), 2)
        self.assertEqual(demanda.servidores_display, "Dr. Thiago")
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("demandas_eventos:editar", args=[demanda.pk]))
        self.assertContains(resposta, 'data-tema="cyberbullying"')
        self.assertContains(resposta, 'name="temas" value="%s" checked' % outro.pk)

    def test_formulario_usa_campos_de_horario(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("demandas_eventos:nova"))
        self.assertContains(resposta, 'type="time"', count=1)
        self.assertNotContains(resposta, 'name="periodo_evento_texto"')

    def test_form_rejeita_periodo_invertido(self):
        form = DemandaEventoForm(self.dados_post(data_fim_evento="2026-09-01"), usuario=self.usuario)
        self.assertFalse(form.is_valid())
        self.assertIn("data_fim_evento", form.errors)

    def test_solicitante_com_texto_legado_extenso_e_preservado(self):
        self.assertEqual(DemandaEvento._meta.get_field("solicitante").max_length, 1000)
        demanda = self.criar_demanda(solicitante="A" * 500)
        self.assertEqual(len(demanda.solicitante), 500)

    def test_cria_edita_e_registra_andamento_no_historico(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(reverse("demandas_eventos:nova"), self.dados_post())
        demanda = DemandaEvento.objects.get(solicitante="Colégio Estadual")
        self.assertRedirects(resposta, reverse("demandas_eventos:editar", args=[demanda.pk]))
        # A linha fica com o setor de quem registrou, sem campo na tela.
        self.assertEqual(list(demanda.setores.all()), [self.ascom])
        self.assertEqual(demanda.status, StatusDemanda.PENDENTE)
        self.assertEqual(demanda.telefone, "(41) 99999-0000")
        self.assertEqual(demanda.email, "colegio@example.org")
        resposta = self.client.get(reverse("demandas_eventos:editar", args=[demanda.pk]))
        self.assertContains(resposta, "Editar palestra")
        self.assertContains(resposta, 'name="novo_status"')
        self.assertContains(resposta, "vg-stepper")
        self.assertNotContains(resposta, 'name="status"')

        url = reverse("demandas_eventos:andamento", args=[demanda.pk])
        palestrante = Palestrante.objects.create(nome="Servidor Exemplo")
        resposta = self.client.post(url, {"novo_status": StatusDemanda.EVENTO_AGENDADO, "andamento": "Palestrante confirmado", "andamento_palestrante": palestrante.pk})
        self.assertRedirects(resposta, reverse("demandas_eventos:editar", args=[demanda.pk]) + "#sec-andamento", fetch_redirect_response=False)
        demanda.refresh_from_db()
        self.assertEqual(demanda.status, StatusDemanda.EVENTO_AGENDADO)
        self.assertEqual(demanda.andamento, "Palestrante confirmado")
        ultimo = demanda.historico.last()
        self.assertEqual((ultimo.acao, ultimo.status_anterior, ultimo.descricao), ("TRANSICAO", "PENDENTE", "Palestrante confirmado"))
        # Como na planilha, a linha atendida continua editável.
        self.client.post(url, {"novo_status": StatusDemanda.ATENDIDA})
        self.assertEqual(
            self.client.get(reverse("demandas_eventos:editar", args=[demanda.pk])).status_code, 200
        )

    def test_andamento_em_modal_a_partir_da_lista(self):
        demanda = self.criar_demanda()
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("demandas_eventos:lista"))
        url = reverse("demandas_eventos:andamento", args=[demanda.pk])
        self.assertContains(resposta, f'href="{url}" data-cadastro-modal')
        self.assertContains(resposta, "data-cadastro-dialog")
        modal = {"HTTP_X_CADASTRO_MODAL": "1"}
        resposta = self.client.get(url, **modal)
        self.assertTemplateUsed(resposta, "pages/demandas_eventos/_modal_andamento.html")
        self.assertContains(resposta, 'name="novo_status"')
        resposta = self.client.post(url, {"novo_status": "", "andamento": ""}, **modal)
        self.assertContains(resposta, "Escolha o novo status.")
        resposta = self.client.post(url, {"novo_status": "EM_ANDAMENTO", "andamento": "Contato feito"}, **modal)
        self.assertEqual(resposta.json(), {"ok": True})
        demanda.refresh_from_db()
        self.assertEqual(demanda.status, "EM_ANDAMENTO")

    def test_telefone_precisa_de_ddd(self):
        form = DemandaEventoForm(self.dados_post(telefone="9999-0000"), usuario=self.usuario)
        self.assertFalse(form.is_valid())
        self.assertIn("telefone", form.errors)
        form = DemandaEventoForm(self.dados_post(email="nao-e-email"), usuario=self.usuario)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

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
        self.assertEqual(str(demanda.hora_inicio), "14:00:00")
        self.assertEqual(demanda.periodo_evento_texto, "")
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
        self.assertFalse(usado.temas.exists())
        self.assertIn("Tema: Crimes virtuais", usado.informacoes_previas)
        # O texto livre da coluna Tema não vira tema novo.
        antiga = DemandaEvento.objects.get(solicitante="Delegacia Teste")
        self.assertFalse(antiga.temas.exists())
        self.assertIn("Tema: Segurança", antiga.informacoes_previas)

    def test_colunas_dos_anos_anteriores_vao_para_informacoes_previas(self):
        call_command("importar_planilha_ascom", str(self.arquivo))
        antiga = DemandaEvento.objects.get(solicitante="Delegacia Teste")
        self.assertEqual(antiga.evento, TipoEventoPalestra.EVENTO)
        # "Dr. Fulano" não está na aba PALESTRANTES: o nome fica como texto.
        self.assertEqual(antiga.servidor, "Dr. Fulano")
        self.assertEqual(antiga.canal_solicitacao, "EMAIL")
        self.assertEqual(antiga.quantidade_publico, 80)
        for trecho in ("Tipo de evento: Inauguração", "Unidade: NUCIBER", "Briefing: Briefing antigo",
                       "Matéria no site: https://site", "Responsável pelo atendimento: Maria"):
            self.assertIn(trecho, antiga.informacoes_previas)
