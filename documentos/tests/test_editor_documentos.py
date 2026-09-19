"""Editor documental em todos os documentos: termo (do cadastro e do ofício),
justificativa, ordem de serviço, plano de trabalho, relatório técnico e
diário de bordo. Cada um abre no editor embutido no fim do formulário, marca os trechos com a
origem e grava na origem — o termo, o texto da justificativa, a OS, o plano,
o relatório da prestação, a linha do diário."""
import json
from datetime import date

from django.test import TestCase
from django.urls import reverse

from documentos.models import DocumentoBloco
from viagens_oficios.tests.fixtures import CenarioOficioMixin


class EditorEmTodosOsDocumentosTests(CenarioOficioMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.oficio = self.criar()

    # Utilitários
    def pagina(self, chave, pk, v=""):
        """O editor embutido (o que o cartão do formulário busca)."""
        url = reverse("documentos:editor_embutido", args=[chave, pk]) + (f"?v={v}" if v else "")
        return self.client.get(url)

    def folha(self, chave, pk, v=""):
        url = reverse("documentos:editor_folha", args=[chave, pk]) + (f"?v={v}" if v else "")
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200, resposta.content[:500])
        return resposta.content.decode()

    def patch(self, chave, pk, campo, valores, *, v="", objeto=None, especie="campo"):
        url = reverse(f"documentos:editor_{especie}", args=[chave, pk, campo])
        parametros = [p for p in (f"v={v}" if v else "", f"objeto={objeto}" if objeto else "") if p]
        if parametros:
            url += "?" + "&".join(parametros)
        return self.client.patch(url, data=json.dumps({"valores": valores}), content_type="application/json")

    # Termo
    def termo(self):
        from viagens_termos.models import TermoAutorizacao

        termo = TermoAutorizacao.objects.create(oficio=self.oficio, destino_estado=self.uf, destino_cidade=self.destino,
                                                data_evento_inicio=date(2026, 9, 10), viatura=self.viatura)
        termo.servidores.set([self.a])
        return termo

    def test_termo_do_cadastro_abre_no_editor_e_grava_no_termo(self):
        termo = self.termo()
        r = self.pagina("termo_autorizacao", termo.pk, self.a.pk)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, f"/documentos/editor/termo_autorizacao/{termo.pk}/folha/?v={self.a.pk}")
        folha = self.folha("termo_autorizacao", termo.pk, self.a.pk)
        for campo in ("termo_periodo", "termo_destino", "viatura_modelo", "servidor_nome"):
            self.assertIn(f'data-doc-campo="{campo}"', folha)
        self.assertIn(f'data-doc-origem="servidor" data-doc-objeto="{self.a.pk}"', folha)
        self.assertIn('data-doc-bloco="declaracao"', folha)

        r = self.patch("termo_autorizacao", termo.pk, "termo_periodo", {"data_evento_inicio": "2026-09-12", "data_evento_fim": ""}, v=self.a.pk)
        self.assertEqual(r.status_code, 200, r.content)
        termo.refresh_from_db()
        self.assertEqual((termo.data_evento_inicio, termo.data_evento_fim), (date(2026, 9, 12), date(2026, 9, 12)))
        self.assertIn("12 de setembro", r.json()["folha"])

    def test_termo_de_servidor_fora_dele_e_404(self):
        termo = self.termo()
        self.assertEqual(self.pagina("termo_autorizacao", termo.pk, self.b.pk).status_code, 404)

    def test_texto_do_modelo_do_termo_vai_para_o_pdf(self):
        from documentos.services.document_context import contexto_de_payload
        from documentos.services.types import DocumentoTipo
        from viagens_termos.services import _legacy_docx_context, build_termo_cadastro_payload

        termo = self.termo()
        r = self.patch("termo_autorizacao", termo.pk, "declaracao", {"conteudo": "Declaração reescrita."}, v=self.a.pk, especie="bloco")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(DocumentoBloco.objects.filter(termo=termo, chave="declaracao", editado_manualmente=True).exists())
        # A geração põe os blocos no payload: o PDF sai com o texto reescrito.
        from viagens_termos import services

        payload = build_termo_cadastro_payload(termo, self.a)
        payload["documento"] = services._conteudo_documental(termo)
        contexto = contexto_de_payload(DocumentoTipo.TERMO_AUTORIZACAO, payload, _legacy_docx_context(payload))
        self.assertEqual(contexto["blocos"]["declaracao"]["conteudo"], "Declaração reescrita.")

    def test_termo_do_oficio_muda_o_cadastro_do_servidor(self):
        r = self.pagina("termo_oficio", self.oficio.pk, self.a.pk)
        self.assertEqual(r.status_code, 200)
        folha = self.folha("termo_oficio", self.oficio.pk, self.a.pk)
        self.assertIn('data-doc-campo="roteiro"', folha)
        r = self.patch("termo_oficio", self.oficio.pk, "servidor_telefone", {"telefone": "41999998888"}, v=self.a.pk, objeto=self.a.pk)
        self.assertEqual(r.status_code, 200, r.content)
        self.a.refresh_from_db()
        self.assertIn("41999998888", self.a.telefone.replace("(", "").replace(")", "").replace(" ", "").replace("-", ""))

    # Justificativa
    def test_justificativa_grava_o_texto_pelo_servico(self):
        from viagens_oficios.models import Justificativa

        folha = self.folha("justificativa", self.oficio.pk)
        self.assertIn('data-doc-campo="justificativa_texto"', folha)
        r = self.patch("justificativa", self.oficio.pk, "justificativa_texto", {"texto": "Primeira linha.\n\nSegunda linha."})
        self.assertEqual(r.status_code, 200, r.content)
        j = Justificativa.objects.get(oficio=self.oficio)
        self.assertIn("Segunda linha.", j.texto)
        self.assertEqual(j.status, Justificativa.STATUS_FINALIZADA)
        self.assertIn("Segunda linha.", r.json()["folha"])

    def test_justificativa_vazia_volta_com_erro(self):
        r = self.patch("justificativa", self.oficio.pk, "justificativa_texto", {"texto": ""})
        self.assertEqual(r.status_code, 400)
        self.assertIn("texto", r.json()["erros"])

    # Ordem de serviço
    def ordem(self):
        from viagens_ordens.models import OrdemServico

        ordem = OrdemServico.objects.create(tipo_necessidade=OrdemServico.TIPO_PADRAO, data_evento_inicio=date(2026, 9, 10),
                                            data_evento_fim=date(2026, 9, 11), motivo="Apoio ao evento")
        ordem.servidores.set([self.a])
        ordem.destinos.set([self.destino])
        return ordem

    def test_ordem_de_servico_grava_motivo_e_equipe(self):
        ordem = self.ordem()
        folha = self.folha("ordem_servico", ordem.pk)
        for campo in ("os_tipo", "os_equipe", "os_periodo", "os_motivo", "os_destinos"):
            self.assertIn(f'data-doc-campo="{campo}"', folha)
        self.assertIn('data-doc-bloco="atribuicoes"', folha)
        r = self.patch("ordem_servico", ordem.pk, "os_motivo", {"motivo": "Cobertura da feira"})
        self.assertEqual(r.status_code, 200, r.content)
        r = self.patch("ordem_servico", ordem.pk, "os_equipe", {"servidores": [str(self.a.pk), str(self.b.pk)]})
        self.assertEqual(r.status_code, 200, r.content)
        ordem.refresh_from_db()
        self.assertEqual(ordem.motivo, "Cobertura da feira")
        self.assertEqual(set(ordem.servidores.values_list("pk", flat=True)), {self.a.pk, self.b.pk})

    def test_bloco_da_ordem_fica_na_ordem(self):
        ordem = self.ordem()
        r = self.patch("ordem_servico", ordem.pk, "determino", {"conteudo": "Determino e ordeno"}, especie="bloco")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(DocumentoBloco.objects.filter(ordem_servico=ordem, chave="determino").exists())
        self.assertIn("Determino e ordeno", r.json()["folha"])

    def test_destinos_da_ordem_so_levam_a_tela_da_ordem(self):
        ordem = self.ordem()
        r = self.client.get(reverse("documentos:editor_campo", args=["ordem_servico", ordem.pk, "os_destinos"]))
        self.assertEqual(r.status_code, 200)
        self.assertIn(reverse("viagens_ordens:editar", args=[ordem.pk]), r.json()["fragmento"])
        self.assertNotIn('type="submit"', r.json()["fragmento"])

    # Plano de trabalho
    def test_texto_do_plano_escrito_no_documento_fica_e_apagar_volta_ao_automatico(self):
        from viagens_planos.services import criar_plano_rascunho

        plano = criar_plano_rascunho()
        r = self.patch("plano_trabalho", plano.pk, "plano_contextualizacao", {"contextualizacao": "Texto meu."})
        self.assertEqual(r.status_code, 200, r.content)
        plano.refresh_from_db()
        self.assertEqual(plano.contextualizacao, "Texto meu.")
        self.assertFalse(plano.contextualizacao_auto)
        r = self.patch("plano_trabalho", plano.pk, "plano_contextualizacao", {"contextualizacao": ""})
        self.assertEqual(r.status_code, 200, r.content)
        plano.refresh_from_db()
        self.assertTrue(plano.contextualizacao_auto)
        self.assertNotEqual(plano.contextualizacao, "")

    # Prestação: relatório técnico e diário
    def servidor_da_prestacao(self):
        from viagens_prestacoes.models import PrestacaoContas, PrestacaoServidor

        prestacao, _ = PrestacaoContas.objects.get_or_create(oficio=self.oficio)
        ps, _ = PrestacaoServidor.objects.get_or_create(prestacao=prestacao, servidor=self.a)
        return ps

    def test_relatorio_nasce_ao_gravar_e_abrir_nao_grava(self):
        from viagens_prestacoes.models import RelatorioTecnico

        ps = self.servidor_da_prestacao()
        folha = self.folha("relatorio_tecnico", ps.pk)
        self.assertIn('data-doc-campo="rt_conclusao"', folha)
        self.assertFalse(RelatorioTecnico.objects.filter(prestacao=ps.prestacao).exists())
        r = self.patch("relatorio_tecnico", ps.pk, "rt_conclusao", {"conclusao": "Missão cumprida."})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(RelatorioTecnico.objects.get(prestacao=ps.prestacao).conclusao, "Missão cumprida.")

    def test_diaria_recebida_invalida_volta_com_o_erro_do_servico(self):
        ps = self.servidor_da_prestacao()
        r = self.patch("relatorio_tecnico", ps.pk, "rt_diaria", {"diaria": "muito"})
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("diaria", r.json()["erros"])

    def test_diario_grava_km_na_linha(self):
        ps = self.servidor_da_prestacao()
        folha = self.folha("diario_bordo", ps.pk)
        from viagens_prestacoes.models import DiarioBordo

        trecho = DiarioBordo.objects.get(prestacao=ps.prestacao).trechos.first()
        self.assertIn(f'data-doc-campo="diario_km" data-doc-origem="trecho" data-doc-objeto="{trecho.pk}"', folha)
        r = self.patch("diario_bordo", ps.pk, "diario_km", {"km_inicial": "1200", "abastecimento": "True"}, objeto=trecho.pk)
        self.assertEqual(r.status_code, 200, r.content)
        trecho.refresh_from_db()
        self.assertEqual((trecho.km_inicial, trecho.abastecimento), (1200, True))

    def test_trecho_de_outro_diario_e_404(self):
        ps = self.servidor_da_prestacao()
        self.folha("diario_bordo", ps.pk)
        r = self.patch("diario_bordo", ps.pk, "diario_km", {"km_inicial": "1"}, objeto=999999)
        self.assertEqual(r.status_code, 404)

    # O editor no fim dos formulários
    def test_formulario_do_oficio_traz_o_editor_de_cada_documento(self):
        r = self.client.get(reverse("viagens_oficios:editar", args=[self.oficio.pk]))
        self.assertContains(r, 'id="documento-justificativa"')
        self.assertContains(r, reverse("documentos:editor_embutido", args=["justificativa", self.oficio.pk]))
        self.assertContains(r, f'id="documento-termo_oficio-{self.a.pk}"')
        self.assertContains(r, reverse("documentos:editor_embutido", args=["termo_oficio", self.oficio.pk]) + f"?v={self.a.pk}")

    def test_formularios_trazem_o_editor_no_fim(self):
        termo = self.termo()
        ordem = self.ordem()
        ps = self.servidor_da_prestacao()
        casos = (
            (reverse("viagens_termos:editar", args=[termo.pk]), f"documento-termo_autorizacao-{self.a.pk}"),
            (reverse("viagens_ordens:editar", args=[ordem.pk]), "documento-ordem_servico"),
            (reverse("viagens_prestacoes:rt_servidor", args=[ps.pk]), "documento-relatorio_tecnico"),
            (reverse("viagens_prestacoes:diario_servidor", args=[ps.pk]), "documento-diario_bordo"),
        )
        for url, cartao in casos:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertContains(r, f'id="{cartao}"')
                self.assertContains(r, "data-de-embutir=")

    def test_endereco_antigo_leva_ao_cartao_no_formulario(self):
        termo = self.termo()
        r = self.client.get(reverse("documentos:editor_pagina", args=["termo_autorizacao", termo.pk]))
        self.assertRedirects(r, reverse("viagens_termos:editar", args=[termo.pk]) + f"#documento-termo_autorizacao-{self.a.pk}", fetch_redirect_response=False)
