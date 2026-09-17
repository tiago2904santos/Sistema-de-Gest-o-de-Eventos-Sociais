"""O contexto do DOCX e a geração de DOCX/PDF pelas views."""

from django.test import TestCase
from django.urls import reverse

from documentos.models import DocumentoArtefato
from documentos.services.adapters.docxtpl_render import render_docx_bytes
from documentos.services.resources_paths import resolve_resource_docx
from viagens_planos.docxtpl_context import build_plano_docxtpl_context
from viagens_planos.models import PlanoTrabalho
from viagens_planos.services import adicionar_evento_ao_plano, aplicar_textos_padrao, atualizar_snapshot_diarias, sincronizar_atividades

from .fixtures import CenarioPlanoMixin

PLACEHOLDERS_DO_MODELO = [
    "numero_plano_trabalho", "unidade", "contextualizacao", "metas", "atividades", "data_evento", "destinos",
    "horario_de_atendimento", "efetivos", "unidade_movel", "valor_do_plano", "recursos_necessarios", "coordenacao",
    "consideracao_final", "sede", "data_extenso", "nome_chefia", "cargo_chefia",
]


class ContextoDocxTests(CenarioPlanoMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plano = self.criar_plano_maringa(efetivo=6)
        self.plano.programa = self.programa
        self.plano.coordenador_adm = self.juliana
        aplicar_textos_padrao(self.plano)
        self.plano.save()
        atualizar_snapshot_diarias(self.plano)

    def test_cobre_todos_os_placeholders(self):
        contexto = build_plano_docxtpl_context(self.plano)
        for chave in PLACEHOLDERS_DO_MODELO:
            self.assertIn(chave, contexto, chave)

    def test_valores_do_exemplo_de_maringa(self):
        contexto = build_plano_docxtpl_context(self.plano)
        self.assertEqual(contexto["numero_plano_trabalho"], "20/2026/ASCOM")
        self.assertEqual(contexto["destinos"], "Maringá/PR")
        self.assertEqual(contexto["data_evento"], "25 a 27 de junho de 2026")
        self.assertEqual(contexto["horario_de_atendimento"], "09:00 até 17:00")
        self.assertEqual(contexto["efetivos"], "6 Policiais Civis (ASCOM)")
        self.assertIn("Valor total: R$7.234,68", contexto["valor_do_plano"])
        self.assertIn("Papiloscopista Juliana Villela de Barros", contexto["coordenacao"])
        self.assertIn("município de Maringá/PR", contexto["contextualizacao"])
        self.assertEqual(contexto["sede"], "Curitiba/PR")
        self.assertEqual(contexto["nome_chefia"], "João Mário Nunes de Góes")
        self.assertEqual(contexto["cargo_chefia"], "Assessor de Comunicação Social")
        self.assertEqual(contexto["metas"], "")
        self.assertEqual(contexto["unidade_movel"], "")

    def test_atividades_entram_nas_metas_e_recursos(self):
        self.plano.atividades_selecionadas.set([self.atividade_cin, self.atividade_movel])
        sincronizar_atividades(self.plano)
        contexto = build_plano_docxtpl_context(self.plano)
        self.assertEqual(contexto["metas"], "• Emitir carteiras de identidade.\n• Levar a estrutura móvel.")
        self.assertIn("• Kit de coleta biométrica.", contexto["recursos_necessarios"])
        self.assertIn("unidade móvel institucional", contexto["recursos_necessarios"])
        self.assertIn("Unidade móvel da PCPR", contexto["unidade_movel"])

    def test_render_docx_com_o_modelo_real(self):
        conteudo = render_docx_bytes(template_path=resolve_resource_docx("plano_trabalho.docx"), context=build_plano_docxtpl_context(self.plano))
        self.assertEqual(conteudo[:2], b"PK")

    def test_render_do_modelo_de_varios_eventos(self):
        adicionar_evento_ao_plano(self.plano)
        self.plano.refresh_from_db()
        contexto = build_plano_docxtpl_context(self.plano)
        self.assertTrue(contexto["is_multi_evento"])
        self.assertEqual(len(contexto["eventos"]), 1)
        self.assertEqual(contexto["eventos"][0]["data_header"], "Dias 25 a 27 de junho de 2026")
        conteudo = render_docx_bytes(template_path=resolve_resource_docx("plano_trabalho_multievento.docx"), context=contexto)
        self.assertEqual(conteudo[:2], b"PK")


class GeracaoPelasViewsTests(CenarioPlanoMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plano = self.criar_plano_maringa()
        self.plano.coordenador_adm = self.juliana
        self.plano.save()
        atualizar_snapshot_diarias(self.plano)

    def test_docx_e_pdf_marcam_o_plano_como_gerado(self):
        r = self.client.post(reverse("viagens_planos:gerar", args=[self.plano.pk, "docx"]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("wordprocessingml", r["Content-Type"])
        r = self.client.post(reverse("viagens_planos:gerar", args=[self.plano.pk, "pdf"]) + "?inline=1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.conteudo(r)[:4], b"%PDF")
        self.assertIn("inline", r["Content-Disposition"])
        self.plano.refresh_from_db()
        self.assertEqual(self.plano.status, PlanoTrabalho.STATUS_GERADO)
        self.assertTrue(DocumentoArtefato.objects.filter(plano_trabalho=self.plano).exists())

    def test_plano_de_varios_eventos_gera_pelo_modelo_proprio(self):
        aplicar_textos_padrao(self.plano)
        self.plano.save()
        adicionar_evento_ao_plano(self.plano)
        self.plano.refresh_from_db()
        self.assertTrue(self.plano.is_multi_evento)
        r = self.client.post(reverse("viagens_planos:gerar", args=[self.plano.pk, "docx"]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.conteudo(r)[:2], b"PK")
        self.assertTrue(DocumentoArtefato.objects.filter(plano_trabalho=self.plano).exists())

    def test_visualizar_entrega_o_pdf_para_o_iframe(self):
        r = self.client.get(reverse("viagens_planos:visualizar", args=[self.plano.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.conteudo(r)[:4], b"%PDF")

    def test_plano_incompleto_nao_gera(self):
        self.plano.efetivos.all().delete()
        r = self.client.post(reverse("viagens_planos:gerar", args=[self.plano.pk, "pdf"]), follow=True)
        self.assertContains(r, "Documento não gerado porque o plano está incompleto.")
        self.assertContains(r, "Corrija os itens abaixo antes de finalizar o plano ou gerar DOCX/PDF.")
        self.assertEqual(self.client.get(reverse("viagens_planos:visualizar", args=[self.plano.pk])).status_code, 409)

    def test_plano_cancelado_nao_gera(self):
        self.plano.cancelar("Adiado")
        r = self.client.post(reverse("viagens_planos:gerar", args=[self.plano.pk, "pdf"]), follow=True)
        self.assertContains(r, "Reative o plano antes de gerar documentos.")

    def test_formato_desconhecido_e_404(self):
        self.assertEqual(self.client.post(reverse("viagens_planos:gerar", args=[self.plano.pk, "odt"])).status_code, 404)
