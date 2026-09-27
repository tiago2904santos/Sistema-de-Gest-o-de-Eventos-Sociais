"""Modelos de texto do relatório técnico: catálogo no padrão dos cadastros
(seção Modelos), com as rotas antigas das prestações redirecionando para lá.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from viagens_prestacoes.models import ModeloTextoRelatorioTecnico
from viagens_prestacoes.test_helpers import autorizar_viagens

from .test_helpers import PrestacaoTestCase as TestCase

CAMPO = ModeloTextoRelatorioTecnico.CAMPO_MOTIVO
LISTA = reverse("viagens_cadastros:lista", args=["modelos-texto-rt"])


class ModelosDeTextoRTTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="rt_modelos", password="123456")
        autorizar_viagens(self.user)
        self.user.groups.add(Group.objects.get(name="VIAGENS_OPERADOR"))
        self.client.force_login(self.user)

    def _criar(self, nome="Modelo A", campo=CAMPO):
        return ModeloTextoRelatorioTecnico.objects.create(nome=nome, texto="Texto do modelo", campo=campo)

    def test_rotas_antigas_levam_ao_catalogo(self):
        modelo = self._criar()
        r = self.client.get(reverse("viagens_prestacoes:modelos_index"))
        self.assertRedirects(r, LISTA, fetch_redirect_response=False)
        retorno = "/viagens/prestacoes/servidor-prestacao/41/rt/"
        r = self.client.get(reverse("viagens_prestacoes:modelos_index"), {"next": retorno})
        self.assertRedirects(r, LISTA + "?next=%2Fviagens%2Fprestacoes%2Fservidor-prestacao%2F41%2Frt%2F", fetch_redirect_response=False)
        r = self.client.get(reverse("viagens_prestacoes:modelo_update", args=[modelo.pk]))
        self.assertRedirects(r, reverse("viagens_cadastros:editar", args=["modelos-texto-rt", modelo.pk]), fetch_redirect_response=False)

    def test_catalogo_no_padrao_dos_cadastros_na_secao_modelos(self):
        self._criar()
        self._criar(nome="Modelo do objetivo", campo=ModeloTextoRelatorioTecnico.CAMPO_ATIVIDADE)
        r = self.client.get(LISTA)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "<h1>Modelos</h1>")
        self.assertContains(r, "Modelos de texto do RT")
        self.assertContains(r, "Modelo A")
        self.assertContains(r, "Descrição do evento")
        self.assertContains(r, "Objetivo da participação")
        self.assertContains(r, "Novo modelo de texto")
        self.assertContains(r, "data-cadastro-dialog")
        # Trilha da seção: os três catálogos de modelos, não as tabelas de cadastro.
        self.assertEqual([g["slug"] for g in r.context["grupos"]], ["motivos-oficio", "modelos-justificativa", "modelos-texto-rt"])
        # Navegação: "Modelos" aceso, "Cadastros" não.
        self.assertContains(r, 'aria-current="page" aria-haspopup="true">Modelos</a>')
        self.assertNotContains(r, 'aria-current="page" aria-haspopup="true">Cadastros</a>')

    def test_modal_cria_e_edita_com_o_campo_do_relatorio(self):
        r = self.client.get(reverse("viagens_cadastros:novo", args=["modelos-texto-rt"]), HTTP_X_CADASTRO_MODAL="1")
        self.assertTemplateUsed(r, "pages/viagens_cadastros/_modal_form.html")
        self.assertContains(r, 'name="campo"')
        self.assertContains(r, "Conclusão")
        # Nada de ativo/inativo nem de ordem nos modelos.
        self.assertNotContains(r, 'name="ordem"')
        self.assertNotContains(r, 'name="ativo"')
        r = self.client.post(reverse("viagens_cadastros:novo", args=["modelos-texto-rt"]),
                             {"campo": ModeloTextoRelatorioTecnico.CAMPO_CONCLUSAO, "nome": "Encerramento", "texto": "Concluiu-se."},
                             HTTP_X_CADASTRO_MODAL="1")
        self.assertEqual(r.json(), {"ok": True})
        modelo = ModeloTextoRelatorioTecnico.objects.get(nome="Encerramento")
        self.assertEqual(modelo.campo, ModeloTextoRelatorioTecnico.CAMPO_CONCLUSAO)
        r = self.client.post(reverse("viagens_cadastros:editar", args=["modelos-texto-rt", modelo.pk]),
                             {"campo": modelo.campo, "nome": "Encerramento", "texto": "Concluiu-se, enfim."},
                             HTTP_X_CADASTRO_MODAL="1")
        self.assertEqual(r.json(), {"ok": True})
        modelo.refresh_from_db()
        self.assertEqual(modelo.texto, "Concluiu-se, enfim.")

    def test_exclusao_pelas_duas_rotas(self):
        modelo = self._criar()
        r = self.client.post(reverse("viagens_prestacoes:modelo_delete", args=[modelo.pk]))
        self.assertRedirects(r, LISTA, fetch_redirect_response=False)
        self.assertFalse(ModeloTextoRelatorioTecnico.objects.filter(pk=modelo.pk).exists())
        outro = self._criar(nome="Modelo B")
        r = self.client.post(reverse("viagens_cadastros:excluir", args=["modelos-texto-rt", outro.pk]))
        self.assertIn(r.status_code, (200, 302))
        self.assertFalse(ModeloTextoRelatorioTecnico.objects.filter(pk=outro.pk).exists())

    def test_gaveta_de_modelos_na_navegacao(self):
        r = self.client.get(reverse("viagens_prestacoes:index"))
        for rotulo in ["Motivos de ofício", "Modelos de justificativa", "Modelos de texto do RT"]:
            self.assertContains(r, rotulo)
        self.assertContains(r, LISTA)
        self.assertNotContains(r, reverse("viagens_prestacoes:modelos_index"))


class ModeloPadraoDoRTTests(TestCase):
    """Um modelo padrão por campo do RT entra sozinho no relatório em branco,
    com os marcadores trocados pelos dados do ofício (m118)."""

    def setUp(self):
        from decimal import Decimal

        from viagens_cadastros.models import Cargo, Servidor
        from viagens_oficios.models import Oficio
        from viagens_prestacoes.models import PrestacaoContas
        from viagens_roteiros.models import Roteiro

        self.user = get_user_model().objects.create_user(username="rt_padrao", password="123456")
        autorizar_viagens(self.user)
        self.user.groups.add(Group.objects.get(name="VIAGENS_OPERADOR"))
        self.client.force_login(self.user)
        cargo = Cargo.objects.create(nome="Agente")
        self.servidor = Servidor.objects.create(nome="Servidor A", cargo=cargo, cpf="11122233344")
        roteiro = Roteiro.objects.create(valor_diarias=Decimal("100.00"))
        self.oficio = Oficio.objects.create(numero=7, ano=2026, protocolo="123456789", roteiro=roteiro, motivo="COBERTURA DO EVENTO")
        self.oficio.servidores.add(self.servidor)
        self.prestacao = PrestacaoContas.objects.get(oficio=self.oficio)

    def test_padrao_e_um_por_campo(self):
        a = ModeloTextoRelatorioTecnico.objects.create(nome="A", texto="a", campo=ModeloTextoRelatorioTecnico.CAMPO_CONCLUSAO, is_padrao=True)
        outro_campo = ModeloTextoRelatorioTecnico.objects.create(nome="M", texto="m", campo=ModeloTextoRelatorioTecnico.CAMPO_MEDIDAS, is_padrao=True)
        b = ModeloTextoRelatorioTecnico.objects.create(nome="B", texto="b", campo=ModeloTextoRelatorioTecnico.CAMPO_CONCLUSAO, is_padrao=True)
        a.refresh_from_db(); outro_campo.refresh_from_db()
        self.assertEqual((a.is_padrao, b.is_padrao, outro_campo.is_padrao), (False, True, True))

    def test_relatorio_em_branco_recebe_o_padrao_com_marcadores_e_texto_escrito_fica(self):
        from viagens_prestacoes.models import RelatorioTecnico
        from viagens_prestacoes.services import garantir_campos_padrao_relatorio_tecnico

        ModeloTextoRelatorioTecnico.objects.create(nome="Objetivo", texto="Participar de {motivo} com {servidores}.",
                                                   campo=ModeloTextoRelatorioTecnico.CAMPO_ATIVIDADE, is_padrao=True)
        ModeloTextoRelatorioTecnico.objects.create(nome="Fecho", texto="Concluiu-se.", campo=ModeloTextoRelatorioTecnico.CAMPO_CONCLUSAO, is_padrao=True)
        ModeloTextoRelatorioTecnico.objects.create(nome="Solto", texto="Não é padrão.", campo=ModeloTextoRelatorioTecnico.CAMPO_MEDIDAS)
        relatorio = RelatorioTecnico.objects.create(prestacao=self.prestacao, conclusao="Já escrito.")
        atualizados = garantir_campos_padrao_relatorio_tecnico(relatorio)
        relatorio.refresh_from_db()
        self.assertIn("atividade", atualizados)
        self.assertEqual(relatorio.atividade, "Participar de COBERTURA DO EVENTO com SERVIDOR A.")
        self.assertEqual(relatorio.conclusao, "Já escrito.")
        self.assertEqual(relatorio.medidas, "")

    def test_padrao_pelo_catalogo(self):
        modelo = ModeloTextoRelatorioTecnico.objects.create(nome="A", texto="a", campo=ModeloTextoRelatorioTecnico.CAMPO_CONCLUSAO)
        r = self.client.post(reverse("viagens_cadastros:definir_padrao", args=["modelos-texto-rt", modelo.pk]))
        self.assertEqual(r.status_code, 302)
        modelo.refresh_from_db()
        self.assertTrue(modelo.is_padrao)
        self.assertContains(self.client.get(LISTA), '<span class="st st--padrao">Padrão</span>', status_code=200)
