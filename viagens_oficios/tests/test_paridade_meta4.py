"""Meta 4 — Justificativas: a tela do app `justificativas` da origem.

Lista das justificativas com a regra de prazo e o estado do texto, inclusão
rápida (vários ofícios, um modelo, um texto), busca de ofícios pelo servidor
com teto de 30, exclusão do texto, e os catálogos já cobertos na Meta 3.
"""

from django.urls import reverse

from viagens_oficios.models import Justificativa, ModeloJustificativa, Oficio

from .test_paridade_meta3 import Cenario


class JustificativasTests(Cenario):
    def url(self, **params):
        return self.client.get(reverse("viagens_oficios:justificativas"), params)

    def test_lista_mostra_regra_texto_e_acoes(self):
        exigido = self.oficio(dias=3, protocolo="123456789", servidores=[self.janine])
        folgado = self.oficio(dias=20, justificativa="teste 1")
        r = self.url()
        self.assertContains(r, f"Nº {exigido.numero_formatado} · Protocolo 12.345.678-9")
        self.assertContains(r, "Obrigatória")
        self.assertContains(r, "Não exigida")
        self.assertContains(r, "Antecedência (3 dias) igual ou inferior ao prazo mínimo (10 dias).")
        self.assertContains(r, "Pendente")
        self.assertContains(r, "Nenhuma justificativa informada.")
        self.assertContains(r, "Preenchida")
        self.assertContains(r, "teste 1")
        self.assertContains(r, f"Editar justificativa do ofício {exigido.numero_formatado}")
        self.assertContains(r, f"Abrir documentos da justificativa do ofício {folgado.numero_formatado}")
        self.assertContains(r, f"Excluir justificativa do ofício {folgado.numero_formatado}")
        self.assertNotContains(r, f"Excluir justificativa do ofício {exigido.numero_formatado}")
        self.assertContains(r, "Inclusão rápida")
        self.assertContains(r, "2 justificativas")

    def test_filtros_por_situacao_e_busca(self):
        pendente = self.oficio(dias=3)
        preenchida = self.oficio(dias=3, justificativa="Determinação superior")
        r = self.url(situacao="pendentes")
        self.assertContains(r, f"Nº {pendente.numero_formatado}")
        self.assertNotContains(r, f"Nº {preenchida.numero_formatado}")
        r = self.url(situacao="preenchidas")
        self.assertContains(r, f"Nº {preenchida.numero_formatado}")
        self.assertNotContains(r, f"Nº {pendente.numero_formatado}")
        r = self.url(q="Determinação")
        self.assertContains(r, f"Nº {preenchida.numero_formatado}")
        self.assertNotContains(r, f"Nº {pendente.numero_formatado}")
        r = self.url(q="Antonina")
        self.assertContains(r, f"Nº {pendente.numero_formatado}")
        r = self.url(q="ZZZ")
        self.assertContains(r, "Nenhuma justificativa")
        self.assertContains(r, "Nenhuma justificativa encontrada com os filtros aplicados.")

    def test_busca_de_oficios_devolve_ate_trinta(self):
        for _ in range(31):
            self.oficio(dias=3, servidores=[self.janine])
        cancelado = self.oficio(dias=3, cancelar=True)
        r = self.client.get(reverse("viagens_oficios:justificativas_buscar_oficios"), {"q": "JANINE"})
        dados = r.json()
        self.assertEqual(len(dados["results"]), 30)
        self.assertTrue(dados["truncado"])
        self.assertEqual(dados["limite"], 30)
        self.assertTrue(all(item["main"].startswith("Ofício ") for item in dados["results"]))
        self.assertNotIn(cancelado.pk, [item["id"] for item in dados["results"]])
        r = self.client.get(reverse("viagens_oficios:justificativas_buscar_oficios"), {"q": "12.345"})
        self.assertEqual(r.json()["results"], [])

    def test_inclusao_rapida_aplica_a_varios_oficios(self):
        modelo = ModeloJustificativa.objects.create(nome="DEMANDA URGENTE", texto="Texto do modelo", is_padrao=True)
        a, b = self.oficio(dias=3), self.oficio(dias=5)
        r = self.client.post(reverse("viagens_oficios:justificativas"), {
            "rapida-oficios": [str(a.pk), str(b.pk)], "rapida-modelo": str(modelo.pk),
            "rapida-texto": "  Determinação   superior  ", "next": reverse("viagens_oficios:justificativas") + "?situacao=preenchidas",
        })
        self.assertRedirects(r, reverse("viagens_oficios:justificativas") + "?situacao=preenchidas")
        for o in (a, b):
            j = Justificativa.objects.get(oficio=o)
            self.assertEqual(j.texto, "Determinação superior")
            self.assertEqual(j.modelo, modelo)
            self.assertEqual(j.status, Justificativa.STATUS_FINALIZADA)
            self.assertTrue(j.obrigatoria)

    def test_inclusao_rapida_invalida_reabre_o_painel_com_os_escolhidos(self):
        a = self.oficio(dias=3, protocolo="123456789")
        r = self.client.post(reverse("viagens_oficios:justificativas"), {"rapida-oficios": [str(a.pk)], "rapida-texto": ""})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Informe o texto da justificativa.")
        self.assertContains(r, f'value="{a.pk}"')
        self.assertContains(r, "Não foi possível aplicar a justificativa")
        r = self.client.post(reverse("viagens_oficios:justificativas"), {"rapida-texto": "Só texto"})
        self.assertContains(r, "Escolha ao menos um ofício.")

    def test_excluir_limpa_o_texto_e_mantem_a_regra(self):
        o = self.oficio(dias=3, justificativa="Apagar")
        j = o.justificativa
        volta = reverse("viagens_oficios:justificativas") + "?q=x"
        r = self.client.post(reverse("viagens_oficios:justificativa_excluir", args=[j.pk]), {"next": volta})
        self.assertRedirects(r, volta)
        j.refresh_from_db()
        self.assertEqual(j.texto, "")
        self.assertIsNone(j.modelo)
        self.assertEqual(j.status, Justificativa.STATUS_RASCUNHO)
        self.assertTrue(j.obrigatoria)
        self.assertEqual(Oficio.objects.filter(pk=o.pk).count(), 1)

    def test_leitor_consulta_sem_escrever(self):
        o = self.oficio(dias=3, justificativa="x")
        self.user.groups.clear()
        r = self.url()
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Inclusão rápida")
        self.assertNotContains(r, "Excluir justificativa")
        self.assertEqual(self.client.post(reverse("viagens_oficios:justificativas"), {"rapida-texto": "x"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("viagens_oficios:justificativa_excluir", args=[o.justificativa.pk])).status_code, 403)

    def test_item_de_navegacao(self):
        r = self.url()
        self.assertContains(r, 'aria-current="page">Justificativas</a>')
        r = self.client.get(reverse("viagens_oficios:lista"))
        self.assertContains(r, 'aria-current="page">Ofícios</a>')
        self.assertNotContains(r, 'aria-current="page">Justificativas</a>')
