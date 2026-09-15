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
        for texto in [self.oficio.numero_formatado, "20.260.000-1", "JANINE LACERDA DO PRADO", "JOÃO MARIO DE GOES",
                      "Número da solicitação de JANINE LACERDA DO PRADO", "Definir período das diárias de JANINE LACERDA DO PRADO",
                      'placeholder="Solicitação"', "Enviar aviso de liberação de diárias por WhatsApp", "Placa", "Modelo",
                      "Abrir prestação na etapa 1", "Documentos e downloads", "Escolher documentos para baixar",
                      "Anexar documentos assinados", "Finalizar prestação", "Arquivar prestação", "Pacote final (PDF)",
                      "Buscar por servidor, ofício, protocolo ou solicitação…", "Não liberadas (2)", "Liberadas (0)",
                      "Arquivados (0)", "Finalizados (0)", 'class="st st--pc-pendente">Pendente']:
            self.assertContains(r, texto)
        self.assertContains(r, reverse("viagens_prestacoes:diario_servidor", args=[self.ps_janine.pk]))
        self.assertContains(r, reverse("viagens_prestacoes:documentos_servidor", args=[self.ps_janine.pk]))
        self.assertContains(r, reverse("viagens_prestacoes:prestacao_servidor_finalizar", args=[self.ps_janine.pk]))
        self.assertContains(r, reverse("viagens_prestacoes:prestacao_servidor_arquivar", args=[self.ps_janine.pk]))
        self.assertContains(r, reverse("viagens_prestacoes:prestacao_servidor_solicitacao_autosave", args=[self.ps_janine.pk]))
        self.assertNotContains(r, "<table")

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
        self.assertContains(r, "10/08 → 24/08/2026")
        self.assertContains(r, 'value="123456"')
        self.assertContains(r, "✓ Comprovante")
        self.assertContains(r, "Gerenciar documentos assinados")
        self.assertContains(r, "Anexado: saque.pdf")
        self.assertContains(r, 'class="of-tag">Motorista')
        self.assertContains(r, "Liberadas (1)")
        self.assertContains(r, "Não liberadas (1)")

    def test_situacoes_e_busca(self):
        self.ps_joao.definir_finalizada(True)
        r = self.lista(aba="finalizados")
        self.assertEqual([c["ps_pk"] for c in r.context["cards"]], [self.ps_joao.pk])
        self.assertContains(r, "Finalizada")
        r = self.lista(q="JANINE")
        self.assertEqual([c["ps_pk"] for c in r.context["cards"]], [self.ps_janine.pk])
        r = self.lista(q="ZZZ")
        self.assertContains(r, "Nenhuma prestação encontrada.")
        self.assertContains(r, "Limpar")

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
        r = self.lista()
        self.assertContains(r, "Reabrir prestação")
        r = self.client.post(reverse("viagens_prestacoes:prestacao_servidor_arquivar", args=[self.ps_joao.pk]), {"next": volta})
        self.assertRedirects(r, volta)
        self.assertContains(self.lista(aba="arquivados"), "Desarquivar prestação")

    def test_leitor_ve_os_cartoes_sem_os_comandos(self):
        self.user.groups.clear()
        r = self.lista()
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Abrir prestação na etapa 1")
        self.assertNotContains(r, "Finalizar prestação")
        self.assertNotContains(r, "Anexar documentos assinados")
        self.assertNotContains(r, 'placeholder="Solicitação"')
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
        for texto in ["Etapa 1", "Diário de Bordo", "Etapas da prestação", "Equipe", "JOÃO MARIO DE GOES", "Motorista e viatura",
                      "Trocar motorista / viatura", "Ajustar roteiro realizado", "Visualizar PDF", "Baixar planilha", "Deslocamentos",
                      'name="form-0-km_inicial"', 'name="form-0-km_final"', 'name="form-0-abastecimento"', 'value="sim" selected',
                      "Salvar e continuar para o RT", 'data-autosave-model="diario_bordo"']:
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

    def test_relatorio_tecnico_por_blocos(self):
        r = self.client.get(reverse("viagens_prestacoes:rt_servidor", args=[self.ps_janine.pk]))
        for texto in ["Etapa 2", "Relatório Técnico", "Custeio", 'name="diaria"', 'name="translado"', 'name="translado_outro"', 'name="combustivel"', 'name="passagem"',
                      "Descrição do evento", "Objetivo da participação", "Conclusão", "Medidas a serem adotadas pelo órgão", "Informações complementares",
                      'name="modelo_motivo"', 'name="motivo"', "Modelos de texto", "Diária recebida por este servidor", f'ps-{self.ps_janine.pk}-diaria_valor_override',
                      "Visualizar PDF", "Baixar DOCX", "Baixar PDF", "Salvar relatório", "Salvar e continuar", 'data-autosave-model="relatorio_tecnico"']:
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
        for texto in ["Etapa 3", "Documentos e fechamento", "Solicitação e liberação das diárias", "Número da solicitação",
                      "Data de liberação das diárias", "Prazo limite para saque",
                      "Despacho assinado", "Ofício assinado", "Comprovante de saque ou transferência", "Relatório técnico assinado", "Diário de bordo assinado",
                      "Compartilhado pela equipe do ofício", "Só de JANINE LACERDA DO PRADO", "Voltar ao RT",
                      "Pacote final e fechamento", "Falta para fechar o PDF final", "Informe o número da solicitação",
                      "Documentos de JANINE LACERDA DO PRADO", "Finalizar prestação", "Arquivar prestação"]:
            self.assertContains(r, texto)
        self.assertContains(r, 'type="file"', count=5)
        self.assertNotContains(r, "Baixar pacote (PDF final)")
        self.assertNotContains(r, "Etapa 4")


class ModelosDeTextoTests(CenarioPrestacoes):
    def test_catalogo_por_campo(self):
        ModeloTextoRelatorioTecnico.objects.create(nome="Modelo A", texto="Texto A", campo=ModeloTextoRelatorioTecnico.CAMPO_MOTIVO)
        r = self.client.get(reverse("viagens_prestacoes:modelos_index"))
        for texto in ['aria-label="Campos do relatório"', "<h2>Modelo A</h2>", "Texto A", "Novo modelo de descrição do evento", "Salvar modelo", "Editar modelo Modelo A", "Excluir modelo Modelo A", 'data-confirmar="Confirmar exclusão?"']:
            self.assertContains(r, texto)
        r = self.client.post(reverse("viagens_prestacoes:modelos_index"), {"quick_add_campo": "conclusao", "modelo-conclusao-campo": "conclusao", "modelo-conclusao-nome": "Fecho", "modelo-conclusao-texto": "Concluímos."})
        self.assertEqual(r.status_code, 302)
        modelo = ModeloTextoRelatorioTecnico.objects.get(nome="Fecho")
        self.assertEqual(modelo.campo, "conclusao")
        r = self.client.get(reverse("viagens_prestacoes:modelo_update", args=[modelo.pk]))
        self.assertContains(r, "Editar modelo")
        self.assertContains(r, 'value="Fecho"')
        self.assertContains(r, "Concluímos.")
        r = self.client.post(reverse("viagens_prestacoes:modelo_delete", args=[modelo.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ModeloTextoRelatorioTecnico.objects.filter(pk=modelo.pk).exists())
