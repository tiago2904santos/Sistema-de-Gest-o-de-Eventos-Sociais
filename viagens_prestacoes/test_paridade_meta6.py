"""Meta 6 — Prestações de contas: as telas do app `prestacoes_contas` da origem.

A lista com um cartão por servidor (cabeçalho do ofício, selo, solicitação e
período das diárias, motorista, comprovante, WhatsApp, placa e modelo,
trechos, valor e quantidade de diárias, os cinco comandos), as três etapas por
servidor com as barras de etapas e equipe no topo (diário de bordo, troca de
motorista/viatura, relatório técnico, documentos e fechamento), os modelos de
texto do relatório no padrão de catálogo e o que o leitor não pode.
"""

from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from viagens_prestacoes.models import DiarioBordo, ModeloTextoRelatorioTecnico, PrestacaoDocumentoAnexo
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin, pdf_minimo


class CenarioPrestacoes(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.janine = self.criar_servidor("JANINE LACERDA DO PRADO")
        self.joao = self.criar_servidor("JOÃO MARIO DE GOES")
        self.fixture = self.criar_prestacao(numero=1, servidores=[self.janine, self.joao])
        self.oficio = self.fixture.oficio
        self.ps_janine, self.ps_joao = self.fixture.prestacoes_servidor

    def lista(self, **params):
        return self.client.get(reverse("viagens_prestacoes:index"), params)


class ListaPrestacoesTests(CenarioPrestacoes):
    def test_cartao_mostra_o_que_a_origem_mostra(self):
        r = self.lista()
        self.assertEqual(len(r.context["cards"]), 2)
        # Situações na trilha; um bloco por ofício com a linha do ofício e, embaixo, cada servidor
        # com os campos da solicitação e do período do saque (autosave) e o menu de ações.
        for texto in [self.oficio.numero_formatado, "20.260.000-1", "JANINE LACERDA DO PRADO", "JOÃO MARIO DE GOES",
                      "Ações de JANINE LACERDA DO PRADO", "Protocolo", "Destino", "Prazo de saque",
                      f'name="ps-{self.ps_janine.pk}-numero_solicitacao"', f'name="ps-{self.ps_janine.pk}-data_liberacao_diarias"',
                      f'name="ps-{self.ps_janine.pk}-prazo_limite_saque"', "Avisar por WhatsApp", "Abrir prestação", "Abrir ofício",
                      "Anexar documentos assinados", "<b>Finalizar prestação</b>", "<b>Arquivar prestação</b>",
                      "Buscar por servidor, ofício, protocolo ou solicitação", "Situação das prestações",
                      'class="st st--pc-pendente">Pendente', 'placeholder="0000000"']:
            self.assertContains(r, texto)
        self.assertEqual({g["slug"]: g["total"] for g in r.context["situacoes"]},
                         {"todas": 2, "nao_liberadas": 2, "liberadas": 0, "arquivados": 0, "finalizados": 0, "saque_vencendo": 0, "prestacao_vencida": 0})
        self.assertContains(r, reverse("viagens_prestacoes:diario_servidor", args=[self.ps_janine.pk]))
        # Finalizar e arquivar são da prestação do ofício (a equipe toda), no menu da linha do ofício.
        self.assertContains(r, reverse("viagens_prestacoes:prestacao_equipe_acao", args=[self.fixture.prestacao.pk, "finalizar"]))
        self.assertContains(r, reverse("viagens_prestacoes:prestacao_equipe_acao", args=[self.fixture.prestacao.pk, "arquivar"]))
        self.assertNotContains(r, reverse("viagens_prestacoes:prestacao_servidor_finalizar", args=[self.ps_janine.pk]))
        # Janine e João são do mesmo ofício: um bloco só, e cada linha grava sozinha pelo autosave dela.
        self.assertEqual(len(r.context["grupos"]), 1)
        self.assertEqual(r.content.decode().count(f"Ofício {self.oficio.numero_formatado}</h2>"), 1)
        for ps in (self.ps_janine, self.ps_joao):
            self.assertContains(r, reverse("viagens_prestacoes:prestacao_servidor_solicitacao_autosave", args=[ps.pk]))

    def test_periodo_comprovante_e_motorista_no_cartao(self):
        self.ps_janine.data_liberacao_diarias = date(2026, 8, 10)
        self.ps_janine.prazo_limite_saque = date(2026, 8, 24)
        self.ps_janine.numero_solicitacao = "123456"
        self.ps_janine.save()
        PrestacaoDocumentoAnexo.objects.create(prestacao=self.fixture.prestacao, servidor_prestacao=self.ps_janine, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE,
                                               arquivo=SimpleUploadedFile("saque.pdf", pdf_minimo(), content_type="application/pdf"), nome_original="saque.pdf")
        self.oficio.motorista = self.joao
        self.oficio.save(update_fields=["motorista", "atualizado_em"])
        r = self.lista()
        self.assertContains(r, 'value="2026-08-10"')
        self.assertContains(r, 'value="2026-08-24"')
        self.assertContains(r, 'value="123456"')
        self.assertContains(r, 'value="123456"')
        self.assertContains(r, 'Comprovante</span>')
        self.assertContains(r, "Gerenciar documentos assinados")
        # Os modais da lista: o comprovante anexado aparece como assinado no "Baixar documentos"
        # e é uma das opções do "Anexar documento assinado".
        import html as html_lib
        import json
        corpo = r.content.decode()
        inicio = corpo.index('data-itens="', corpo.index(f'/servidor-prestacao/{self.ps_janine.pk}/baixar/')) + len('data-itens="')
        itens = json.loads(html_lib.unescape(corpo[inicio:corpo.index('"', inicio)]))
        self.assertIn({"valor": "comprovante", "assinado": True}, [{"valor": i["valor"], "assinado": i["assinado"]} for i in itens])
        self.assertContains(r, "data-anexar-opcoes=")
        self.assertContains(r, "Baixar documentos")
        url = reverse("viagens_prestacoes:prestacao_baixar", args=[self.ps_janine.pk])
        resposta = self.client.post(url, {"itens": ["comprovante"], "formato": "pdf"})
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertTrue(resposta.content.startswith(b"%PDF"))
        self.assertEqual(self.client.post(url, {"itens": ["inventado"], "formato": "pdf"}).status_code, 404)
        self.assertContains(self.client.post(url, {"formato": "pdf"}, follow=True), "Marque ao menos um documento para baixar.")
        # O motorista do ofício se distingue pelo crachá grafite com o volante.
        self.assertContains(r, "pc-linha__av pc-linha__av--motorista", count=1)
        self.assertContains(r, 'class="pc-chip pc-chip--feito"')
        totais = {g["slug"]: g["total"] for g in r.context["situacoes"]}
        self.assertEqual((totais["liberadas"], totais["nao_liberadas"]), (1, 1))

    def test_situacoes_e_busca(self):
        self.ps_joao.definir_finalizada(True)
        r = self.lista(aba="finalizados")
        self.assertEqual([c["ps_pk"] for c in r.context["cards"]], [self.ps_joao.pk])
        self.assertContains(r, "Finalizada")
        r = self.lista(q="JANINE")
        self.assertEqual([c["ps_pk"] for c in r.context["cards"]], [self.ps_janine.pk])
        r = self.lista(q="ZZZ")
        self.assertContains(r, "Nenhuma prestação encontrada.")
        # A busca guarda a situação escolhida na trilha.
        r = self.lista(aba="finalizados", q="ZZZ")
        self.assertContains(r, '<input type="hidden" name="aba" value="finalizados">')

    def test_solicitacao_grava_pelo_formulario_e_pelo_autosave(self):
        volta = reverse("viagens_prestacoes:index") + "?aba=liberadas"
        r = self.client.post(reverse("viagens_prestacoes:index"), {"action": "save_solicitacoes", f"ps-{self.ps_janine.pk}-numero_solicitacao": "SOL-9",
                                                                     f"ps-{self.ps_janine.pk}-data_liberacao_diarias": "2026-08-10", f"ps-{self.ps_janine.pk}-prazo_limite_saque": "2026-08-24", "next": volta})
        self.assertRedirects(r, volta)
        self.ps_janine.refresh_from_db()
        self.assertEqual(self.ps_janine.numero_solicitacao, "SOL-9")
        self.assertEqual(self.ps_janine.prazo_limite_saque, date(2026, 8, 24))

    def test_finalizar_e_arquivar_voltam_para_onde_estavam(self):
        volta = reverse("viagens_prestacoes:index") + "?q=JANINE"
        r = self.client.post(reverse("viagens_prestacoes:prestacao_servidor_finalizar", args=[self.ps_janine.pk]), {"next": volta})
        self.assertRedirects(r, volta)
        self.ps_janine.refresh_from_db()
        self.assertTrue(self.ps_janine.finalizada)
        # Finalizar um servidor não reabre o menu da equipe: ele só oferece reabrir com todos finalizados.
        r = self.lista()
        self.assertContains(r, "<b>Finalizar prestação</b>")
        r = self.client.post(reverse("viagens_prestacoes:prestacao_servidor_arquivar", args=[self.ps_joao.pk]), {"next": volta})
        self.assertRedirects(r, volta)
        self.assertContains(self.lista(aba="arquivados"), "Ações da prestação do ofício")

    def test_menu_do_oficio_finaliza_e_arquiva_a_equipe_toda(self):
        r = self.lista()
        self.assertContains(r, f"Ações da prestação do ofício {self.oficio.numero_formatado}")
        self.assertContains(r, "Por servidor")
        url = reverse("viagens_prestacoes:prestacao_equipe_acao", args=[self.fixture.prestacao.pk, "finalizar"])
        self.assertContains(r, url)
        volta = reverse("viagens_prestacoes:index") + "?q=JANINE"
        self.assertRedirects(self.client.post(url, {"next": volta}), volta)
        for ps in (self.ps_janine, self.ps_joao):
            ps.refresh_from_db()
            self.assertTrue(ps.finalizada)
        # Com a equipe toda finalizada, o menu oferece reabrir; e reabre todos.
        r = self.lista()
        reabrir = reverse("viagens_prestacoes:prestacao_equipe_acao", args=[self.fixture.prestacao.pk, "reabrir"])
        self.assertContains(r, reabrir)
        self.client.post(reabrir, {"next": volta})
        for ps in (self.ps_janine, self.ps_joao):
            ps.refresh_from_db()
            self.assertFalse(ps.finalizada)
        self.client.post(reverse("viagens_prestacoes:prestacao_equipe_acao", args=[self.fixture.prestacao.pk, "arquivar"]))
        for ps in (self.ps_janine, self.ps_joao):
            ps.refresh_from_db()
            self.assertTrue(ps.arquivada)
        self.assertEqual(self.client.post(reverse("viagens_prestacoes:prestacao_equipe_acao", args=[self.fixture.prestacao.pk, "apagar"])).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.user.groups.clear()
        self.assertEqual(self.client.post(url).status_code, 403)

    def test_leitor_ve_os_cartoes_sem_os_comandos(self):
        self.user.groups.clear()
        r = self.lista()
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Abrir prestação")
        self.assertNotContains(r, "<b>Finalizar prestação</b>")
        self.assertNotContains(r, "Anexar documentos assinados")
        # Quem só consulta lê a solicitação e o período, sem campos nem autosave.
        self.assertNotContains(r, 'placeholder="0000000"')
        self.assertNotContains(r, "data-autosave-url")
        self.assertEqual(self.client.post(reverse("viagens_prestacoes:prestacao_servidor_finalizar", args=[self.ps_janine.pk])).status_code, 403)

    def test_abrir_pelo_oficio_cai_na_etapa_1(self):
        r = self.client.get(reverse("viagens_prestacoes:abrir_oficio", args=[self.oficio.pk]))
        self.assertRedirects(r, reverse("viagens_prestacoes:diario_servidor", args=[self.ps_janine.pk]), fetch_redirect_response=False)


class EtapasTests(CenarioPrestacoes):
    def test_diario_com_barra_de_etapas_e_equipe(self):
        r = self.client.get(reverse("viagens_prestacoes:diario_servidor", args=[self.ps_janine.pk]))
        self.assertEqual(r.status_code, 200)
        # Etapas e equipe são barras no topo: não há lateral flutuante.
        self.assertNotContains(r, "<aside")
        # Enxuta: nome e selo no cabeçalho, a barra das etapas com a atual em destaque, a troca de
        # servidor e um cartão só com o PDF, a planilha e o menu (troca e ajuste do roteiro).
        for texto in ['aria-current="step" title="Diário de Bordo', "Etapas da prestação", "Servidores do ofício", "Trocar de servidor", "JOÃO MARIO DE GOES",
                      "Diário de bordo", "Trechos", "Motorista", "Viatura",
                      "Trocar motorista / viatura", "Ajustar roteiro realizado", "Visualizar PDF", "Baixar planilha",
                      'name="form-0-km_inicial"', 'name="form-0-km_final"', 'name="form-0-abastecimento"', 'value="sim" selected',
                      "Salvar e continuar", 'data-autosave-model="diario_bordo"', "js/trilho.js"]:
            self.assertContains(r, texto)
        # A barra da equipe troca de servidor sem sair da etapa.
        self.assertContains(r, reverse("viagens_prestacoes:diario_servidor", args=[self.ps_joao.pk]))
        self.assertNotContains(r, "_campos.html")
        self.assertNotContains(r, "form_simples")

    def test_troca_de_motorista_e_viatura(self):
        url = reverse("viagens_prestacoes:diario_servidor_motorista", args=[self.ps_janine.pk])
        r = self.client.get(url)
        for texto in ["Trocar motorista / viatura", "Preencher a partir de outro ofício", 'id="dmv-oficios-source"', 'name="motorista_modo"',
                      "Manter motorista do ofício", "Outro servidor deste ofício", "Motorista de outro ofício", 'name="viatura_modo"',
                      "Selecionar do cadastro", "Preencher manualmente", 'name="motorista_manual_cpf"', 'name="viatura_manual_placa"',
                      "Salvar motorista e viatura"]:
            self.assertContains(r, texto)
        r = self.client.post(url, {"motorista_modo": DiarioBordo.MOTORISTA_MODO_OUTRO, "motorista_manual_nome": "  Carlos   Motorista ", "motorista_manual_cpf": "123.456.789-01",
                                   "motorista_oficio_referencia": "15/2026", "viatura_modo": DiarioBordo.VIATURA_MODO_MANUAL, "viatura_manual_modelo": "Onix", "viatura_manual_placa": "abc-1d23"})
        self.assertRedirects(r, reverse("viagens_prestacoes:diario_servidor", args=[self.ps_janine.pk]))
        diario = DiarioBordo.objects.get(prestacao=self.fixture.prestacao)
        self.assertEqual(diario.motorista_manual_nome, "Carlos Motorista")
        self.assertEqual(diario.motorista_manual_cpf, "12345678901")
        self.assertEqual(diario.viatura_manual_placa, "ABC1D23")
        r = self.client.get(reverse("viagens_prestacoes:diario_servidor", args=[self.ps_janine.pk]))
        self.assertContains(r, "Trocados neste diário")
        self.assertContains(r, "Carlos Motorista")
        r = self.client.post(url, {"motorista_modo": DiarioBordo.MOTORISTA_MODO_SERVIDOR})
        self.assertContains(r, "Selecione um servidor do ofício.")
        # O erro volta ao diário com o modal da troca aberto (e o que foi digitado nele).
        self.assertTemplateUsed(r, "pages/viagens_prestacoes/diario_bordo_form.html")
        self.assertContains(r, 'id="pc-dialogo-motorista"')
        self.assertContains(r, " data-abrir>")

    def test_relatorio_tecnico_por_blocos(self):
        r = self.client.get(reverse("viagens_prestacoes:rt_servidor", args=[self.ps_janine.pk]))
        for texto in ['aria-current="step" title="Relatório Técnico', "Relatório Técnico", 'name="diaria"', 'name="translado"', 'name="translado_outro"', 'name="combustivel"', 'name="passagem"',
                      "Descrição do evento", "Objetivo da participação", "Conclusão", "Medidas a serem adotadas pelo órgão", "Informações complementares",
                      'name="modelo_motivo"', 'name="motivo"', "Modelos de texto", f'ps-{self.ps_janine.pk}-diaria_valor_override',
                      "Visualizar PDF", "Baixar PDF", "Voltar ao diário", "Salvar e continuar", 'data-autosave-model="relatorio_tecnico"']:
            self.assertContains(r, texto)
        r = self.client.post(reverse("viagens_prestacoes:rt_servidor", args=[self.ps_janine.pk]), {"diaria": "R$ 200,00", "translado": "Não houve", "combustivel": "__outro__", "combustivel_outro": "R$ 120,00",
                                                                                                     "passagem": "Não houve", "motivo": "Cobertura do evento", "atividade": "Registro fotográfico", "continuar": "1"})
        self.assertRedirects(r, reverse("viagens_prestacoes:documentos_servidor", args=[self.ps_janine.pk]))
        relatorio = self.fixture.prestacao.relatorio_tecnico
        self.assertEqual(relatorio.combustivel, "R$ 120,00")
        r = self.client.get(reverse("viagens_prestacoes:rt_servidor", args=[self.ps_joao.pk]))
        self.assertContains(r, "Registro fotográfico")

    def test_documentos_e_fechamento_na_mesma_etapa(self):
        """A etapa do PDF final deixou de ser uma tela: fecha dentro de Documentos."""
        r = self.client.get(reverse("viagens_prestacoes:documentos_servidor", args=[self.ps_janine.pk]))
        # Um cartão só: solicitação e prazo de saque numa linha, os cinco documentos em linhas, o que
        # falta para o pacote final e um botão de ação (baixar documentos, pacote final, arquivar).
        for texto in ['aria-current="step" title="Documentos e fechamento', "Documentos e fechamento", "Número da solicitação",
                      "Prazo de saque", f'name="ps-{self.ps_janine.pk}-data_liberacao_diarias"', f'name="ps-{self.ps_janine.pk}-prazo_limite_saque"',
                      "Despacho assinado", "Ofício assinado", "Comprovante de saque ou transferência", "Relatório técnico assinado", "Diário de bordo assinado",
                      "Voltar ao relatório",
                      "Falta para o pacote final", "Informe o número da solicitação",
                      "Baixar documentos", "Pacote final (PDF)", "Finalizar prestação", "Arquivar prestação"]:
            self.assertContains(r, texto)
        import re
        # Fora o modal de anexar assinado do shell, que existe em toda página.
        self.assertEqual(re.sub(r'<dialog class="an-dialogo"[^>]*data-anexar-dialogo.*?</dialog>', '', r.content.decode(), flags=re.S).count('type="file"'), 5)
        self.assertNotContains(r, "Baixar pacote (PDF final)")
        self.assertNotContains(r, "Etapa 4")


class ModelosDeTextoTests(CenarioPrestacoes):
    def test_catalogo_por_campo(self):
        """Os modelos do RT viraram um catálogo da seção Modelos (padrão dos
        cadastros); as rotas das prestações levam para lá."""
        ModeloTextoRelatorioTecnico.objects.create(nome="Modelo A", texto="Texto A", campo=ModeloTextoRelatorioTecnico.CAMPO_MOTIVO)
        lista = reverse("viagens_cadastros:lista", args=["modelos-texto-rt"])
        r = self.client.get(reverse("viagens_prestacoes:modelos_index"), follow=True)
        self.assertRedirects(r, lista)
        for texto in ["Modelo A", "Descrição do evento", "Novo modelo de texto"]:
            self.assertContains(r, texto)
        r = self.client.post(reverse("viagens_cadastros:novo", args=["modelos-texto-rt"]),
                             {"campo": "conclusao", "nome": "Fecho", "texto": "Concluímos."}, HTTP_X_CADASTRO_MODAL="1")
        self.assertEqual(r.json(), {"ok": True})
        modelo = ModeloTextoRelatorioTecnico.objects.get(nome="Fecho")
        self.assertEqual(modelo.campo, "conclusao")
        r = self.client.get(reverse("viagens_cadastros:editar", args=["modelos-texto-rt", modelo.pk]), HTTP_X_CADASTRO_MODAL="1")
        self.assertContains(r, 'value="Fecho"')
        self.assertContains(r, "Concluímos.")
        r = self.client.post(reverse("viagens_prestacoes:modelo_delete", args=[modelo.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ModeloTextoRelatorioTecnico.objects.filter(pk=modelo.pk).exists())
