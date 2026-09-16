"""Termos de autorização — a tela única e a coluna única.

O termo deixou de ter tela de detalhe: a lista abre direto no formulário, e o
que só existia no detalhe (documentos para baixar por servidor, o genérico, o
da viatura, os lotes, a anexação do assinado, os documentos já gerados, a
prévia em tela e o cancelamento/reativação/exclusão) virou seção do próprio
formulário, visível só quando se edita um termo já salvo.

As asserções de conteúdo aqui são as mesmas que o detalhe garantia em
`viagens_oficios/tests/test_paridade_meta5.py`, reapontadas para a nova
navegação — nada de cobertura foi descartado.
"""

from django.urls import NoReverseMatch, reverse

from documentos.models import DocumentoArtefato
from viagens_termos.models import TermoAutorizacao
from viagens_oficios.tests.test_paridade_meta5 import CenarioTermos


TEMPLATES_DO_MODULO = ["lista.html", "form.html", "preview.html"]


class RotaDeDetalheTests(CenarioTermos):
    def test_rota_de_detalhe_nao_existe_mais(self):
        t = self.termo(cidade=self.antonina, inicio=self.data(3))
        with self.assertRaises(NoReverseMatch):
            reverse("viagens_termos:detalhe", args=[t.pk])

    def test_lista_abre_no_formulario(self):
        o = self.oficio(dias=3, servidores=[self.janine], viatura=self.duster)
        t = self.termo(oficio=o)
        r = self.lista()
        editar = reverse("viagens_termos:editar", args=[t.pk])
        self.assertContains(r, f'href="{editar}#documentos"')
        self.assertContains(r, "Todos os documentos")
        self.assertContains(r, editar + "?next=")

    def test_leitor_abre_a_previa(self):
        t = self.termo(cidade=self.antonina, inicio=self.data(3), servidores=[self.janine])
        self.user.groups.clear()
        r = self.lista()
        self.assertContains(r, "Abrir")
        self.assertContains(r, reverse("viagens_termos:preview", args=[t.pk]))
        self.assertEqual(self.client.get(reverse("viagens_termos:preview", args=[t.pk])).status_code, 200)


class SecoesDoRegistroNoFormularioTests(CenarioTermos):
    def test_termo_novo_nao_tem_as_secoes_do_registro(self):
        r = self.client.get(reverse("viagens_termos:novo"))
        for texto in ["Escolher documentos para baixar", "Documentos gerados", "Prévia em tela",
                      "Cancelamento e exclusão", "Excluir termo"]:
            self.assertNotContains(r, texto)
        self.assertContains(r, "Salvar termo")
        self.assertContains(r, "Voltar")

    def test_formulario_do_termo_salvo_traz_o_que_era_do_detalhe(self):
        o = self.oficio(dias=-20, protocolo="123456789", servidores=[self.janine, self.joao], viatura=self.duster)
        t = self.termo(oficio=o)
        r = self.client.get(reverse("viagens_termos:editar", args=[t.pk]))
        for texto in [f"Termo #{t.pk}", "Realizado", "Este termo herda do ofício",
                      "Escolher documentos para baixar", "Termo por servidor", "JANINE LACERDA DO PRADO",
                      "JOÃO MARIO DE GOES", "Visualizar", "Anexar assinado", "Termo genérico",
                      "Só destino e período, semipreenchido", "Termo da viatura",
                      "AAA-1234 DUSTER, campos do servidor em branco", "Todos os termos", "2 servidores",
                      "PDF único", "ZIP de PDFs", "ZIP de DOCX", "Documentos gerados",
                      "Nenhum documento gerado.", "Cancelamento", "Cancelar termo", "Excluir termo",
                      "Prévia em tela", "Abrir prévia"]:
            self.assertContains(r, texto)
        self.assertContains(r, reverse("viagens_termos:preview", args=[t.pk]))
        self.assertContains(r, reverse("viagens_termos:todos_pdf", args=[t.pk]))
        self.assertContains(r, reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]) + "?inline=1")
        self.assertContains(r, reverse("viagens_termos:acao", args=[t.pk, "cancelar"]))
        self.assertContains(r, reverse("viagens_termos:acao", args=[t.pk, "excluir"]))

    def test_formularios_secundarios_ficam_fora_do_form_principal(self):
        """HTML válido: nada de `<form>` aninhado no formulário do cadastro."""
        o = self.oficio(dias=3, servidores=[self.janine], viatura=self.duster)
        t = self.termo(oficio=o)
        html = self.client.get(reverse("viagens_termos:editar", args=[t.pk])).content.decode()
        principal = html.index('id="form-termo"')
        fecha = html.index("</form>", principal)
        corpo = html[principal:fecha]
        self.assertNotIn("<form", corpo)
        # E as seções migradas vêm depois desse fechamento.
        for ancora in ['id="documentos"', 'id="gerados"', 'id="previa"', 'id="cancelamento"']:
            self.assertGreater(html.index(ancora), fecha)

    def test_documentos_gerados_aparecem_na_mesma_tela(self):
        o = self.oficio(dias=3, servidores=[self.janine], viatura=self.duster)
        t = self.termo(oficio=o)
        self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]))
        art = DocumentoArtefato.objects.get(termo=t, servidor=self.janine, formato="pdf")
        r = self.client.get(reverse("viagens_termos:editar", args=[t.pk]))
        self.assertNotContains(r, "Nenhum documento gerado.")
        self.assertContains(r, reverse("documentos:baixar", args=[art.pk]))
        self.assertContains(r, reverse("viagens_oficios:assinatura_artefato", args=[art.pk]))

    def test_termo_cancelado_mostra_motivo_e_reativacao(self):
        t = self.termo(cidade=self.antonina, inicio=self.data(3), servidores=[self.janine], cancelar=True)
        r = self.client.get(reverse("viagens_termos:editar", args=[t.pk]))
        self.assertContains(r, "Termo cancelado")
        self.assertContains(r, "Adiado")
        self.assertContains(r, "Reativar termo")
        self.assertContains(r, "reative para emitir documentos.")
        self.assertNotContains(r, "PDF único")

    def test_anexar_assinado_volta_para_o_formulario(self):
        o = self.oficio(dias=3, servidores=[self.janine])
        t = self.termo(oficio=o)
        self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]))
        art = DocumentoArtefato.objects.get(termo=t, servidor=self.janine, formato="pdf")
        r = self.client.get(reverse("viagens_oficios:assinatura_artefato", args=[art.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, reverse("viagens_termos:editar", args=[t.pk]))


class NavegacaoTests(CenarioTermos):
    def test_salvar_vai_para_a_lista(self):
        o = self.oficio(dias=3, servidores=[self.janine], viatura=self.duster)
        t = self.termo(oficio=o)
        r = self.client.post(reverse("viagens_termos:editar", args=[t.pk]),
                             {"oficio": o.pk, "viatura": "", "servidores": [str(self.janine.pk)]})
        self.assertRedirects(r, reverse("viagens_termos:lista"))
        t.refresh_from_db()
        self.assertEqual(list(t.servidores.all()), [self.janine])

    def test_cancelar_do_formulario_vai_para_a_lista(self):
        t = self.termo(cidade=self.antonina, inicio=self.data(3))
        r = self.client.get(reverse("viagens_termos:editar", args=[t.pk]))
        self.assertEqual(r.context["url_voltar"], reverse("viagens_termos:lista"))
        self.assertContains(r, f'href="{reverse("viagens_termos:lista")}"')

    def test_acoes_cancelar_reativar_excluir(self):
        t = self.termo(cidade=self.antonina, inicio=self.data(3), servidores=[self.janine])
        editar = reverse("viagens_termos:editar", args=[t.pk])
        r = self.client.post(reverse("viagens_termos:acao", args=[t.pk, "cancelar"]), {"motivo": "Evento adiado"})
        self.assertRedirects(r, editar)
        t.refresh_from_db()
        self.assertTrue(t.cancelado)
        r = self.client.get(editar)
        self.assertContains(r, "Termo cancelado")
        self.assertContains(r, "Evento adiado")
        self.assertContains(r, "Reativar termo")
        r = self.client.post(reverse("viagens_termos:acao", args=[t.pk, "reativar"]))
        self.assertRedirects(r, editar)
        t.refresh_from_db()
        self.assertFalse(t.cancelado)
        self.assertEqual(self.client.post(reverse("viagens_termos:acao", args=[t.pk, "outra"])).status_code, 404)
        volta = reverse("viagens_termos:lista") + "?q=x"
        r = self.client.post(reverse("viagens_termos:acao", args=[t.pk, "excluir"]), {"next": volta})
        self.assertRedirects(r, volta)

    def test_geracao_bloqueada_volta_para_o_formulario(self):
        t = self.termo(cidade=self.antonina, inicio=self.data(3), servidores=[self.janine], cancelar=True)
        r = self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]), follow=True)
        self.assertRedirects(r, reverse("viagens_termos:editar", args=[t.pk]))
        self.assertContains(r, "Reative o termo e o ofício antes de gerar documentos.")
        self.assertFalse(DocumentoArtefato.objects.filter(termo=t).exists())

    def test_previa_volta_para_o_formulario(self):
        o = self.oficio(dias=3, servidores=[self.janine], viatura=self.duster)
        t = self.termo(oficio=o)
        r = self.client.get(reverse("viagens_termos:preview", args=[t.pk]))
        self.assertContains(r, "Voltar ao termo")
        self.assertContains(r, reverse("viagens_termos:editar", args=[t.pk]))


class ColunaUnicaTests(CenarioTermos):
    """Nenhuma tela do módulo tem menu lateral flutuante."""

    def paginas(self):
        o = self.oficio(dias=3, servidores=[self.janine], viatura=self.duster)
        t = self.termo(oficio=o)
        return {
            "lista": self.lista(),
            "novo": self.client.get(reverse("viagens_termos:novo")),
            "editar": self.client.get(reverse("viagens_termos:editar", args=[t.pk])),
            "preview": self.client.get(reverse("viagens_termos:preview", args=[t.pk])),
        }

    def test_sem_aside_sticky_nem_grade_com_lateral(self):
        for nome, r in self.paginas().items():
            with self.subTest(tela=nome):
                self.assertEqual(r.status_code, 200)
                # `d-grade` é o nome exato da classe: `cad-grade`, a grade da trilha de
                # situações da lista (a mesma dos roteiros), contém a mesma substring.
                for marca in ["<aside", 'class="sticky"', "frm-lateral", "frm-grade", 'class="d-grade',
                              "frm-acoes--flut", "step-v"]:
                    self.assertNotContains(r, marca)

    def test_acoes_do_formulario_ficam_no_fim_em_frm_acoes(self):
        r = self.client.get(reverse("viagens_termos:novo"))
        html = r.content.decode()
        principal = html.index('id="form-termo"')
        fecha = html.index("</form>", principal)
        # Como no roteiro: Voltar/Salvar no fim do último cartão do formulário.
        acoes = html.index('<div class="frm-acoes-fim">', principal)
        self.assertLess(acoes, fecha)
        self.assertIn("Salvar termo", html[acoes:fecha])

    def test_salvar_tambem_no_topo_como_no_roteiro(self):
        r = self.client.get(reverse("viagens_termos:novo"))
        html = r.content.decode()
        topo = html.index('class="frm-topo__acoes"')
        self.assertLess(topo, html.index('id="form-termo"'))
        self.assertIn('form="form-termo"', html[topo:topo + 400])
        self.assertContains(r, "Novo termo")


class DestinosNoComponenteDoRoteiroTests(CenarioTermos):
    """Os destinos adicionais usam o componente de destinos do editor de roteiro."""

    def test_linhas_tem_alca_adicionar_e_remover(self):
        r = self.client.get(reverse("viagens_termos:novo"))
        for marca in ["destino-row", "data-destino-alca", "data-destino-adicionar",
                      "data-destino-remover", "data-destinos", "data-destino-modelo"]:
            self.assertContains(r, marca)
        # Uma lista só: a primeira linha é o destino do termo, as outras os adicionais.
        self.assertContains(r, 'name="destino_cidade"')
        self.assertContains(r, "extra_estado___n__")

    def test_ordem_gravada_segue_a_numeracao_que_vem_da_tela(self):
        # O JS renumera as linhas no envio, na ordem em que ficaram na tela;
        # aqui vale conferir que o servidor grava nessa mesma ordem.
        r = self.client.post(reverse("viagens_termos:novo"), {
            "destino_estado": self.pr.pk, "destino_cidade": self.antonina.pk,
            "extra_estado_0": self.pr.pk, "extra_cidade_0": self.curitiba.pk,
            "extra_estado_1": self.pr.pk, "extra_cidade_1": self.antonina.pk,
            "quantidade_destinos": "2",
            "data_evento_inicio": f"{self.data(3):%Y-%m-%d}", "servidores": [str(self.janine.pk)],
        })
        self.assertEqual(r.status_code, 302)
        termo = TermoAutorizacao.objects.get()
        self.assertEqual([d["cidade"] for d in termo.destinos_extras],
                         [self.curitiba.nome, self.antonina.nome])

    def test_linha_removida_na_tela_sai_do_termo(self):
        termo = self.termo(cidade=self.antonina, inicio=self.data(3), servidores=[self.janine])
        termo.destinos_extras = [{"cidade_id": self.curitiba.pk, "estado_id": self.pr.pk,
                                  "cidade": self.curitiba.nome, "estado": self.pr.sigla}]
        termo.save()
        # A tela envia só as linhas que sobraram, renumeradas a partir do zero.
        r = self.client.post(reverse("viagens_termos:editar", args=[termo.pk]), {
            "destino_estado": self.pr.pk, "destino_cidade": self.antonina.pk,
            "quantidade_destinos": "1",
            "data_evento_inicio": f"{self.data(3):%Y-%m-%d}", "servidores": [str(self.janine.pk)],
        })
        self.assertEqual(r.status_code, 302)
        termo.refresh_from_db()
        self.assertEqual(termo.destinos_extras, [])
