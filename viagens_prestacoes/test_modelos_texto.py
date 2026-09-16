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
        r = self.client.post(reverse("viagens_cadastros:novo", args=["modelos-texto-rt"]),
                             {"campo": ModeloTextoRelatorioTecnico.CAMPO_CONCLUSAO, "nome": "Encerramento", "texto": "Concluiu-se.", "ordem": "5"},
                             HTTP_X_CADASTRO_MODAL="1")
        self.assertEqual(r.json(), {"ok": True})
        modelo = ModeloTextoRelatorioTecnico.objects.get(nome="Encerramento")
        self.assertEqual((modelo.campo, modelo.ordem), (ModeloTextoRelatorioTecnico.CAMPO_CONCLUSAO, 5))
        r = self.client.post(reverse("viagens_cadastros:editar", args=["modelos-texto-rt", modelo.pk]),
                             {"campo": modelo.campo, "nome": "Encerramento", "texto": "Concluiu-se, enfim.", "ordem": "5"},
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
