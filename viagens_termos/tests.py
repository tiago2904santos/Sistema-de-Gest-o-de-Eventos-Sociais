"""Termos de autorização — a tela única e a coluna única.

O termo deixou de ter tela de detalhe: a lista abre direto no formulário, e o
que só existia no detalhe (documentos para baixar: o termo vazio, os por servidor e
a anexação do assinado) virou seção
do próprio formulário, visível só quando se edita um termo já salvo. A lista
de arquivos gerados e o cancelamento saíram da tela.

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
                      "JOÃO MARIO DE GOES", "Visualizar", "Anexar assinado", "Termo vazio",
                      "Só destino e período, para preencher à mão", "2 servidores",
                      ]:
            self.assertContains(r, texto)
        for texto in ["Cancelamento e exclusão", "Cancelar termo", 'id="cancelamento"', "Documentos gerados", 'id="gerados"',
                      "Abrir prévia", "PDF único", "ZIP de PDFs", "ZIP de DOCX", 'id="previa"',
                      "Termo genérico", "Termo da viatura"]:
            self.assertNotContains(r, texto)
        html = r.content.decode()
        self.assertLess(html.index("Termo vazio"), html.index("JANINE LACERDA DO PRADO", html.index('id="documentos"')))
        self.assertNotContains(r, reverse("viagens_termos:preview", args=[t.pk]))  # "Abrir prévia" saiu da tela
        self.assertContains(r, reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]) + "?inline=1")
        self.assertNotContains(r, reverse("viagens_termos:acao", args=[t.pk, "cancelar"]))
        self.assertNotContains(r, reverse("viagens_termos:acao", args=[t.pk, "excluir"]))  # excluir fica no menu da lista

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
        for ancora in ['id="documentos"']:
            self.assertGreater(html.index(ancora), fecha)

    def test_pdf_gerado_pode_receber_o_assinado_pela_secao_de_documentos(self):
        o = self.oficio(dias=3, servidores=[self.janine], viatura=self.duster)
        t = self.termo(oficio=o)
        self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]))
        art = DocumentoArtefato.objects.get(termo=t, servidor=self.janine, formato="pdf")
        r = self.client.get(reverse("viagens_termos:editar", args=[t.pk]))
        self.assertNotContains(r, "Documentos gerados")  # a lista de arquivos saiu da tela
        self.assertContains(r, reverse("viagens_oficios:assinatura_artefato", args=[art.pk]))

    def test_termo_cancelado_mostra_motivo_e_reativacao(self):
        t = self.termo(cidade=self.antonina, inicio=self.data(3), servidores=[self.janine], cancelar=True)
        r = self.client.get(reverse("viagens_termos:editar", args=[t.pk]))
        self.assertContains(r, "Termo cancelado")
        self.assertContains(r, "Adiado")
        self.assertNotContains(r, "Reativar termo")  # a seção de cancelamento saiu da tela
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

    def _pdf_do_janine(self):
        o = self.oficio(dias=3, servidores=[self.janine])
        t = self.termo(oficio=o)
        self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]))
        return t, DocumentoArtefato.objects.get(termo=t, servidor=self.janine, formato="pdf")

    def test_links_de_anexar_abrem_o_modal(self):
        t, art = self._pdf_do_janine()
        r = self.client.get(reverse("viagens_termos:editar", args=[t.pk]))
        self.assertContains(r, "data-anexar-dialogo")
        self.assertContains(r, f'href="{reverse("viagens_oficios:assinatura_artefato", args=[art.pk])}" data-anexar-assinado data-anexar-nome="JANINE LACERDA DO PRADO"')
        self.assertContains(r, "Anexar documento assinado")

    def test_anexar_pelo_modal_volta_para_a_pagina_de_origem(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        t, art = self._pdf_do_janine()
        url = reverse("viagens_oficios:assinatura_artefato", args=[art.pk])
        origem = reverse("viagens_termos:lista")
        r = self.client.post(url, {"next": origem, "arquivo": SimpleUploadedFile("assinado.pdf", b"%PDF-1.4 assinado", content_type="application/pdf")})
        self.assertRedirects(r, origem, fetch_redirect_response=False)
        art.refresh_from_db()
        self.assertTrue(art.esta_assinado)
        # Arquivo que não é PDF: volta para a origem com a mensagem, sem anexar outra versão.
        r = self.client.post(url, {"next": origem, "arquivo": SimpleUploadedFile("nota.txt", b"texto", content_type="text/plain")}, follow=True)
        self.assertRedirects(r, origem)
        self.assertContains(r, "Envie um arquivo PDF.")
        self.assertEqual(art.versoes_assinadas.count(), 1)
        # Remover também volta para a origem.
        r = self.client.post(url, {"next": origem, "acao": "remover"})
        self.assertRedirects(r, origem, fetch_redirect_response=False)
        art.refresh_from_db()
        self.assertFalse(art.esta_assinado)

    def test_next_de_fora_do_sistema_e_ignorado(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        t, art = self._pdf_do_janine()
        url = reverse("viagens_oficios:assinatura_artefato", args=[art.pk])
        r = self.client.post(url, {"next": "https://exemplo.com/", "arquivo": SimpleUploadedFile("assinado.pdf", b"%PDF-1.4 x", content_type="application/pdf")})
        self.assertRedirects(r, reverse("viagens_termos:editar", args=[t.pk]), fetch_redirect_response=False)


def pdf_assinado(texto="ASSINADO"):
    """Um PDF de verdade (uma página em branco), com um marcador nos metadados."""
    import io
    from pypdf import PdfWriter
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    escritor.add_metadata({"/Title": texto})
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def corpo(resposta):
    return b"".join(resposta.streaming_content) if resposta.streaming else resposta.content


class AssinadoValeNoLugarDoGeradoTests(CenarioTermos):
    def setUp(self):
        super().setUp()
        o = self.oficio(dias=3, servidores=[self.janine])
        self.t = self.termo(oficio=o)
        self.gerar_pdf = reverse("viagens_termos:gerar", args=[self.t.pk, self.janine.pk, "pdf"])
        self.client.post(self.gerar_pdf)
        self.art = DocumentoArtefato.objects.get(termo=self.t, servidor=self.janine, formato="pdf")
        self.assinado = pdf_assinado()

    def anexar(self, artefato=None, conteudo=None):
        from django.core.files.uploadedfile import SimpleUploadedFile
        url = reverse("viagens_oficios:assinatura_artefato", args=[(artefato or self.art).pk])
        self.client.post(url, {"arquivo": SimpleUploadedFile("assinado.pdf", conteudo or self.assinado, content_type="application/pdf")})

    def test_visualizar_e_baixar_entregam_o_anexado(self):
        self.anexar()
        for url in (self.gerar_pdf, self.gerar_pdf + "?inline=1"):
            r = self.client.post(url)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(corpo(r), self.assinado)
        # Nenhum PDF novo foi gerado para servir o assinado.
        self.assertEqual(DocumentoArtefato.objects.filter(termo=self.t, servidor=self.janine, formato="pdf").count(), 1)

    def test_a_versao_mais_recente_vale(self):
        self.anexar()
        segunda = pdf_assinado("SEGUNDA")
        self.anexar(conteudo=segunda)
        self.assertEqual(corpo(self.client.post(self.gerar_pdf)), segunda)

    def test_pdf_unico_e_zip_usam_o_anexado(self):
        import io
        from zipfile import ZipFile
        from pypdf import PdfReader
        self.anexar()
        r = self.client.post(reverse("viagens_termos:todos_pdf", args=[self.t.pk]))
        # Juntar PDFs descarta os metadados; o anexado se reconhece pela página 200x200.
        self.assertEqual(float(PdfReader(io.BytesIO(r.content)).pages[0].mediabox.width), 200)
        r = self.client.post(reverse("viagens_termos:lote", args=[self.t.pk, "pdf"]))
        with ZipFile(io.BytesIO(r.content)) as z:
            self.assertIn(self.assinado, [z.read(n) for n in z.namelist()])

    def test_docx_continua_sendo_gerado(self):
        self.anexar()
        r = self.client.post(reverse("viagens_termos:gerar", args=[self.t.pk, self.janine.pk, "docx"]))
        self.assertTrue(corpo(r).startswith(b"PK"))

    def test_removido_o_assinado_volta_o_gerado(self):
        self.anexar()
        url = reverse("viagens_oficios:assinatura_artefato", args=[self.art.pk])
        self.client.post(url, {"acao": "remover"})
        conteudo = corpo(self.client.post(self.gerar_pdf))
        self.assertNotEqual(conteudo, self.assinado)
        self.assertTrue(conteudo.startswith(b"%PDF"))

    def test_baixar_documentos_escolhe_entre_assinado_e_original(self):
        url = reverse("viagens_termos:baixar", args=[self.t.pk])
        self.anexar()
        assinado = self.client.post(url, {"itens": [str(self.janine.pk)], "formato": "pdf", "versao": "assinado"})
        self.assertEqual(corpo(assinado), self.assinado)
        original = self.client.post(url, {"itens": [str(self.janine.pk)], "formato": "pdf", "versao": "original"})
        conteudo = corpo(original)
        self.assertTrue(conteudo.startswith(b"%PDF"))
        self.assertNotEqual(conteudo, self.assinado)
        # Sem `versao`, vale o assinado.
        self.assertEqual(corpo(self.client.post(url, {"itens": [str(self.janine.pk)], "formato": "pdf"})), self.assinado)

    def test_modal_sabe_quais_itens_estao_assinados(self):
        import html as html_lib, json
        self.anexar()
        conteudo = self.lista().content.decode()
        inicio = conteudo.index('data-itens="') + len('data-itens="')
        itens = json.loads(html_lib.unescape(conteudo[inicio:conteudo.index('"', inicio)]))
        self.assertEqual({i["nome"]: i["assinado"] for i in itens}, {"Termo vazio": False, "JANINE LACERDA DO PRADO": True})
        self.assertIn('value="original"', conteudo)

    def test_assinado_de_um_documento_nao_vale_para_outro(self):
        self.anexar()
        gerar_vazio = reverse("viagens_termos:gerar", args=[self.t.pk, 0, "pdf"])
        gerar_viatura = reverse("viagens_termos:gerar_viatura", args=[self.t.pk, "pdf"])
        self.assertNotEqual(corpo(self.client.post(gerar_vazio)), self.assinado)
        # Termo vazio e termo da viatura têm os mesmos vínculos; a referência os separa.
        art_vazio = DocumentoArtefato.objects.get(termo=self.t, servidor__isnull=True, formato="pdf")
        vazio_assinado = pdf_assinado("VAZIO")
        self.anexar(art_vazio, vazio_assinado)
        self.assertEqual(corpo(self.client.post(gerar_vazio)), vazio_assinado)
        self.assertNotIn(corpo(self.client.post(gerar_viatura)), (vazio_assinado, self.assinado))


class ChipsDaViaturaTests(CenarioTermos):
    def test_motorista_em_verde_unidade_em_azul(self):
        from viagens_termos.views import opcoes_de_viatura
        opcoes = {o["valor"]: o for o in opcoes_de_viatura()}
        tons = {o["chip_tom"] for o in opcoes.values() if o["chip"]}
        self.assertTrue(tons <= {"atendido", "em_andamento"})
        for o in opcoes.values():
            if not o["chip"]:
                self.assertEqual(o["chip_tom"], "")
            elif o["dados"]["motoristas"]:
                self.assertEqual(o["chip_tom"], "atendido")
            else:
                self.assertEqual(o["chip_tom"], "em_andamento")


class RodapeDoTermoTests(CenarioTermos):
    def test_termo_novo_tem_os_botoes_no_cartao_do_formulario(self):
        html = self.client.get(reverse("viagens_termos:novo")).content.decode()
        fecha = html.index("</form>", html.index('id="form-termo"'))
        self.assertLess(html.index("Salvar termo"), fecha)
        self.assertNotIn('form="form-termo">Salvar termo', html)

    def test_termo_salvo_tem_os_botoes_no_fim_de_documentos(self):
        o = self.oficio(dias=3, servidores=[self.janine])
        t = self.termo(oficio=o)
        html = self.client.get(reverse("viagens_termos:editar", args=[t.pk])).content.decode()
        # Além do Salvar do topo, só um: o do fim de Documentos.
        rodapes = html.count('class="frm-acoes-fim tm-acoes-fim"')
        self.assertEqual(rodapes, 1)
        self.assertGreater(html.index('class="frm-acoes-fim tm-acoes-fim"'), html.index('id="documentos"'))
        self.assertIn('form="form-termo">Salvar termo', html)


class BaixarDocumentosTests(CenarioTermos):
    def setUp(self):
        super().setUp()
        o = self.oficio(dias=3, servidores=[self.janine, self.joao])
        self.t = self.termo(oficio=o)
        self.url = reverse("viagens_termos:baixar", args=[self.t.pk])

    def baixar(self, itens, formato="pdf", saida="separados", **extra):
        return self.client.post(self.url, {"itens": itens, "formato": formato, "saida": saida, **extra})

    def test_modal_recebe_termo_vazio_e_servidores_na_ordem(self):
        import html as html_lib
        import json
        r = self.lista()
        conteudo = r.content.decode()
        inicio = conteudo.index('data-itens="') + len('data-itens="')
        itens = json.loads(html_lib.unescape(conteudo[inicio:conteudo.index('"', inicio)]))
        self.assertEqual([i["nome"] for i in itens], ["Termo vazio", "JANINE LACERDA DO PRADO", "JOÃO MARIO DE GOES"])
        self.assertEqual(itens[0]["valor"], "0")

    def test_um_documento_sai_como_arquivo(self):
        r = self.baixar([str(self.janine.pk)])
        self.assertEqual(r["Content-Type"], "application/pdf")
        r = self.baixar(["0"], formato="docx")
        self.assertIn("wordprocessingml", r["Content-Type"])

    def test_varios_separados_saem_em_zip(self):
        import io
        from zipfile import ZipFile
        r = self.baixar(["0", str(self.janine.pk), str(self.joao.pk)])
        self.assertEqual(r["Content-Type"], "application/zip")
        with ZipFile(io.BytesIO(r.content)) as z:
            self.assertEqual(len(z.namelist()), 3)

    def test_varios_num_pdf_so(self):
        import io
        from pypdf import PdfReader
        r = self.baixar([str(self.janine.pk), str(self.joao.pk)], saida="unico")
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("documentos.pdf", r["Content-Disposition"])
        self.assertGreaterEqual(len(PdfReader(io.BytesIO(r.content)).pages), 2)

    def test_docx_nao_se_junta(self):
        r = self.baixar([str(self.janine.pk), str(self.joao.pk)], formato="docx", saida="unico")
        self.assertEqual(r["Content-Type"], "application/zip")

    def test_nada_marcado_volta_com_mensagem(self):
        origem = reverse("viagens_termos:lista")
        r = self.client.post(self.url, {"formato": "pdf", "next": origem}, follow=True)
        self.assertRedirects(r, origem)
        self.assertContains(r, "Marque ao menos um documento para baixar.")

    def test_servidor_de_fora_ou_formato_estranho_e_404(self):
        self.assertEqual(self.baixar(["999999"]).status_code, 404)
        self.assertEqual(self.baixar(["0"], formato="xlsx").status_code, 404)

    def test_so_via_post_e_so_operador(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.user.groups.clear()
        self.assertEqual(self.baixar(["0"]).status_code, 403)


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
        self.assertNotContains(r, "Reativar termo")  # a seção de cancelamento saiu da tela
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
        acoes = html.index('<div class="frm-acoes-fim tm-acoes-fim">', principal)
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
