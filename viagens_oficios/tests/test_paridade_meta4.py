"""Justificativas — lista no padrão das listas de cadastros, roteiros e termos,
com cadastro e edição num modal (como "Novo servidor").

Lista com a regra de prazo e o estado do texto numa célula só, situações na
trilha, busca, menu de ações por linha; modal de nova justificativa (escolhe
o ofício) e de edição (ofício fixo); exclusão do texto; leitor só consulta.
"""

from django.urls import NoReverseMatch, reverse

from viagens_oficios.models import Justificativa, ModeloJustificativa

from .test_paridade_meta3 import Cenario

MODAL = {"HTTP_X_CADASTRO_MODAL": "1"}


class JustificativasListaTests(Cenario):
    def url(self, **params):
        return self.client.get(reverse("viagens_oficios:justificativas"), params)

    def test_lista_mostra_regra_texto_e_acoes_numa_celula(self):
        exigido = self.oficio(dias=3, protocolo="123456789", servidores=[self.janine])
        folgado = self.oficio(dias=20, justificativa="teste 1")
        r = self.url()
        # Duas linhas: ofício e destino com o estado; período, antecedência e texto.
        self.assertContains(r, f"Ofício {exigido.numero_formatado} · ANTONINA/PR · ")
        self.assertNotContains(r, "Protocolo 12.345.678-9")
        self.assertContains(r, "3 dias de antecedência")
        self.assertContains(r, "20 dias de antecedência")
        self.assertContains(r, "Pendente · exigida")
        self.assertContains(r, "Sem texto")
        self.assertContains(r, "Preenchida")
        self.assertContains(r, 'title="teste 1"')
        self.assertNotContains(r, "Sem modelo")
        # Uma célula de conteúdo e o menu de ações, como em termos.
        self.assertContains(r, '<th>Justificativa</th>')
        self.assertContains(r, f'aria-label="Ações da justificativa do ofício {exigido.numero_formatado}"')
        self.assertContains(r, reverse("viagens_oficios:justificativa_editar", args=[exigido.justificativa.pk]))
        self.assertContains(r, "Preencher justificativa")
        self.assertContains(r, reverse("viagens_oficios:gerar", args=[folgado.pk, "justificativa", "pdf"]))
        self.assertContains(r, reverse("viagens_oficios:justificativa_excluir", args=[folgado.justificativa.pk]))
        self.assertNotContains(r, reverse("viagens_oficios:justificativa_excluir", args=[exigido.justificativa.pk]))
        self.assertContains(r, "Nova justificativa")
        self.assertContains(r, "data-cadastro-dialog")
        self.assertNotContains(r, "Inclusão rápida")

    def test_situacoes_na_trilha_com_contagem_e_busca(self):
        pendente = self.oficio(dias=3)
        preenchida = self.oficio(dias=3, justificativa="Determinação superior")
        r = self.url()
        self.assertEqual([(s["titulo"], s["total"]) for s in r.context["situacoes"]], [("Todas", 2), ("Pendentes", 1), ("Preenchidas", 1)])
        r = self.url(situacao="pendentes")
        self.assertContains(r, f"Ofício {pendente.numero_formatado}")
        self.assertNotContains(r, f"Ofício {preenchida.numero_formatado}")
        r = self.url(situacao="preenchidas")
        self.assertContains(r, f"Ofício {preenchida.numero_formatado}")
        self.assertNotContains(r, f"Ofício {pendente.numero_formatado}")
        r = self.url(q="Determinação")
        self.assertContains(r, f"Ofício {preenchida.numero_formatado}")
        self.assertNotContains(r, f"Ofício {pendente.numero_formatado}")
        r = self.url(q="Antonina")
        self.assertContains(r, f"Ofício {pendente.numero_formatado}")
        r = self.url(q="ZZZ")
        self.assertContains(r, "Nenhuma justificativa encontrada com os filtros aplicados.")

    def test_cancelado_fica_de_fora(self):
        cancelado = self.oficio(dias=3, justificativa="x", cancelar=True)
        self.assertNotContains(self.url(), f"Ofício {cancelado.numero_formatado}")

    def test_inclusao_rapida_e_busca_de_oficios_nao_existem_mais(self):
        with self.assertRaises(NoReverseMatch):
            reverse("viagens_oficios:justificativas_buscar_oficios")
        self.oficio(dias=3)
        r = self.client.post(reverse("viagens_oficios:justificativas"), {"rapida-texto": "x"})
        self.assertEqual(r.status_code, 405)

    def test_leitor_consulta_sem_escrever(self):
        o = self.oficio(dias=3, justificativa="x")
        self.user.groups.clear()
        r = self.url()
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Nova justificativa")
        self.assertNotContains(r, "data-cadastro-dialog")
        self.assertNotContains(r, "Excluir justificativa")
        url = reverse("viagens_oficios:justificativa_editar", args=[o.justificativa.pk])
        self.assertEqual(self.client.get(url, **MODAL).status_code, 403)
        self.assertEqual(self.client.post(url, {"texto": "y"}, **MODAL).status_code, 403)
        self.assertEqual(self.client.post(reverse("viagens_oficios:justificativa_excluir", args=[o.justificativa.pk])).status_code, 403)

    def test_item_de_navegacao(self):
        r = self.url()
        self.assertContains(r, 'aria-current="page">Justificativas</a>')
        r = self.client.get(reverse("viagens_oficios:lista"))
        self.assertContains(r, 'aria-current="page">Ofícios</a>')
        self.assertNotContains(r, 'aria-current="page">Justificativas</a>')


class JustificativaModalTests(Cenario):
    def setUp(self):
        super().setUp()
        self.modelo = ModeloJustificativa.objects.create(nome="Urgência", texto="Viagem urgente </script> por determinação.")

    def test_nova_abre_o_modal_com_os_oficios_sem_texto(self):
        sem_texto = self.oficio(dias=3)
        com_texto = self.oficio(dias=3, justificativa="já tem")
        cancelado = self.oficio(dias=3, cancelar=True)
        r = self.client.get(reverse("viagens_oficios:justificativa_nova"), **MODAL)
        self.assertTemplateUsed(r, "pages/viagens_oficios/_justificativa_modal.html")
        self.assertContains(r, "Nova justificativa")
        self.assertContains(r, 'data-lista-escolha="oficio"')
        self.assertContains(r, 'data-lista-busca="oficio"')
        oficios = [o["valor"] for o in r.context["dados"]["oficios"]]
        self.assertIn(str(sem_texto.pk), oficios)
        self.assertNotIn(str(com_texto.pk), oficios)
        self.assertNotIn(str(cancelado.pk), oficios)
        # O texto do modelo vai escapado para o script.
        self.assertContains(r, 'id="jt-modelos-texto"')
        self.assertNotContains(r, "urgente </script>")
        self.assertEqual(r.context["dados"]["modelos_texto"][str(self.modelo.pk)], self.modelo.texto)

    def test_nova_grava_e_responde_json(self):
        o = self.oficio(dias=3)
        r = self.client.post(reverse("viagens_oficios:justificativa_nova"),
                             {"oficio": o.pk, "modelo": self.modelo.pk, "texto": "  Determinação   superior "}, **MODAL)
        self.assertEqual(r.json(), {"ok": True})
        j = Justificativa.objects.get(oficio=o)
        self.assertEqual((j.texto, j.modelo, j.status), ("Determinação superior", self.modelo, Justificativa.STATUS_FINALIZADA))
        self.assertTrue(j.obrigatoria)
        self.assertEqual(j.dias_antecedencia, 3)

    def test_nova_invalida_volta_o_modal_com_os_erros(self):
        o = self.oficio(dias=3)
        r = self.client.post(reverse("viagens_oficios:justificativa_nova"), {"oficio": o.pk, "texto": "   "}, **MODAL)
        self.assertTemplateUsed(r, "pages/viagens_oficios/_justificativa_modal.html")
        self.assertContains(r, "Informe o texto da justificativa.")
        self.assertContains(r, "Corrija antes de continuar")
        r = self.client.post(reverse("viagens_oficios:justificativa_nova"), {"texto": "x"}, **MODAL)
        self.assertContains(r, "Escolha o ofício.")
        com_texto = self.oficio(dias=3, justificativa="já tem")
        r = self.client.post(reverse("viagens_oficios:justificativa_nova"), {"oficio": com_texto.pk, "texto": "outra"}, **MODAL)
        self.assertContains(r, "Escolha um ofício sem justificativa.")
        self.assertEqual(Justificativa.objects.get(oficio=com_texto).texto, "já tem")

    def test_editar_mostra_o_oficio_fixo_e_grava(self):
        o = self.oficio(dias=20, justificativa="antes")
        url = reverse("viagens_oficios:justificativa_editar", args=[o.justificativa.pk])
        r = self.client.get(url, **MODAL)
        self.assertContains(r, "Editar justificativa")
        self.assertContains(r, f"Ofício Nº {o.numero_formatado}")
        self.assertContains(r, "Não exigida · 20 dias de antecedência (mínimo 10)")
        self.assertContains(r, "antes")
        self.assertNotContains(r, 'name="oficio"')
        r = self.client.post(url, {"texto": "depois", "modelo": ""}, **MODAL)
        self.assertEqual(r.json(), {"ok": True})
        o.justificativa.refresh_from_db()
        self.assertEqual(o.justificativa.texto, "depois")

    def test_sem_javascript_a_lista_abre_com_o_modal(self):
        o = self.oficio(dias=3, justificativa="x")
        r = self.client.get(reverse("viagens_oficios:justificativa_nova"))
        self.assertRedirects(r, reverse("viagens_oficios:justificativas") + "?nova=1")
        r = self.client.get(reverse("viagens_oficios:justificativas"), {"nova": "1"})
        self.assertContains(r, "data-cadastro-inicial")
        self.assertContains(r, "Nova justificativa</h2>")
        url = reverse("viagens_oficios:justificativa_editar", args=[o.justificativa.pk])
        self.assertRedirects(self.client.get(url), reverse("viagens_oficios:justificativas") + f"?editar={o.justificativa.pk}")
        r = self.client.post(url, {"texto": ""})
        self.assertContains(r, "data-cadastro-inicial")
        self.assertContains(r, "Informe o texto da justificativa.")
        r = self.client.post(url, {"texto": "salvo sem js"})
        self.assertRedirects(r, reverse("viagens_oficios:justificativas"))

    def test_excluir_limpa_o_texto_e_mantem_a_regra(self):
        o = self.oficio(dias=3, justificativa="Apagar")
        j = o.justificativa
        volta = reverse("viagens_oficios:justificativas") + "?q=x"
        r = self.client.post(reverse("viagens_oficios:justificativa_excluir", args=[j.pk]), {"next": volta})
        self.assertRedirects(r, volta, fetch_redirect_response=False)
        j.refresh_from_db()
        self.assertEqual((j.texto, j.modelo_id, j.status), ("", None, Justificativa.STATUS_RASCUNHO))
        self.assertEqual(j.oficio_id, o.pk)

    def test_oficio_cancelado_nao_se_edita(self):
        o = self.oficio(dias=3, justificativa="x", cancelar=True)
        url = reverse("viagens_oficios:justificativa_editar", args=[o.justificativa.pk])
        self.assertEqual(self.client.get(url, **MODAL).status_code, 404)
