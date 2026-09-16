"""Meta 5 — Termos de autorização: o app `termos` da origem.

A lista com busca e situações combináveis, os quatro botões de ação, o
cadastro por blocos (ofício vinculado, destino e período, servidores e
viatura, com herança do ofício), o detalhe com os documentos por servidor, o
genérico, o da viatura, todos num PDF só ou em ZIP, a prévia em tela, as
ações cancelar/reativar/excluir e o que o leitor não pode.

O cartão da lista **não** é mais o da origem: o título ficou só com o destino
e o selo temporal, o período saiu de dentro dele, a linha corrida "Ofício: N ·
servidores · placa modelo" virou quatro fatos com ícone e entrou o andamento
dos documentos. Os mesmos dados continuam cobertos aqui, na estrutura nova.
"""

import io
import tempfile
from datetime import timedelta
from zipfile import ZipFile

from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse

from documentos.models import DocumentoArtefato
from viagens_oficios.documents import VarianteTermo
from viagens_termos.models import TermoAutorizacao

from .test_paridade_meta3 import Cenario


class CenarioTermos(Cenario):
    def setUp(self):
        super().setUp()
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=pasta.name, DOCUMENTOS_DEFAULT_PDF_ENGINE="simple"))

    @staticmethod
    def conteudo(resposta):
        return b"".join(resposta.streaming_content) if resposta.streaming else resposta.content

    def termo(self, oficio=None, cidade=None, estado=None, inicio=None, fim=None, servidores=(), viatura=None, cancelar=False):
        t = TermoAutorizacao.objects.create(
            oficio=oficio, destino_cidade=cidade, destino_estado=estado or (cidade.estado if cidade else None),
            data_evento_inicio=inicio, data_evento_fim=fim, viatura=viatura,
        )
        t.servidores.set(servidores)
        if cancelar:
            t.cancelar("Adiado")
        return t

    def lista(self, **params):
        return self.client.get(reverse("viagens_termos:lista"), params)

    def data(self, dias):
        return self.hoje + timedelta(days=dias)


class ListaTermosTests(CenarioTermos):
    def test_cartao_mostra_titulo_selo_fatos_e_heranca(self):
        o = self.oficio(dias=-20, protocolo="123456789", servidores=[self.janine, self.joao], viatura=self.duster)
        t = self.termo(oficio=o)
        r = self.lista()
        inicio, fim = t.periodo_efetivo()
        # O título é só o destino; o período virou um fato, com o seu ícone.
        self.assertContains(r, f'id="termo-{t.pk}-titulo">ANTONINA/PR ')
        self.assertContains(r, 'class="st st--atendido">Realizado')
        for fato in [f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}", f"Ofício {o.numero_formatado}",
                     "JANINE LACERDA DO PRADO, JOÃO MARIO DE GOES", "AAA-1234 DUSTER"]:
            self.assertContains(r, f'<span class="sr-only">')
            self.assertContains(r, fato)
        self.assertContains(r, "Herda do ofício: destino, período, servidores, viatura.")
        # A contagem vive na trilha de situações, como na lista de roteiros.
        self.assertEqual(r.context["situacoes"][0]["total"], 1)

    def test_cartao_nomeia_o_que_falta_em_vez_de_omitir(self):
        """Termo avulso sem servidor nem viatura: os fatos aparecem vazios, não somem."""
        self.termo(cidade=self.antonina, inicio=self.data(3))
        r = self.lista()
        for vazio in ["Termo avulso", "Sem servidores", "Sem viatura"]:
            self.assertContains(r, vazio)
        self.assertContains(r, "tm-fato--ausente")

    def test_cartao_mostra_o_andamento_dos_documentos(self):
        o = self.oficio(dias=3, servidores=[self.janine, self.joao])
        t = self.termo(oficio=o)
        self.assertContains(self.lista(), "Sem PDF gerado")
        self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]))
        self.assertContains(self.lista(), "1 de 2 em PDF")
        self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.joao.pk, "pdf"]))
        self.assertContains(self.lista(), "Todos em PDF")
        art = DocumentoArtefato.objects.filter(termo=t, servidor=self.janine, formato="pdf").first()
        art.arquivo_assinado.save("assinado.pdf", ContentFile(b"%PDF-1.4"), save=True)
        r = self.lista()
        self.assertContains(r, "1 de 2 assinados")
        self.assertContains(r, "Assinado — enviar outra versão")

    def test_selos_de_situacao(self):
        so_uf = self.termo(estado=self.pr, servidores=[self.janine])
        previsto = self.termo(cidade=self.antonina, inicio=self.data(3), fim=self.data(4))
        andamento = self.termo(cidade=self.antonina, inicio=self.data(-1), fim=self.data(1))
        cancelado = self.termo(cidade=self.antonina, inicio=self.data(3), cancelar=True)
        r = self.lista()
        self.assertContains(r, f'id="termo-{so_uf.pk}-titulo">PR <span class="st st--neutro">Sem período</span>')
        self.assertContains(r, f'id="termo-{previsto.pk}-titulo">ANTONINA/PR <span class="st st--aguardando">Previsto</span>')
        self.assertContains(r, f'id="termo-{andamento.pk}-titulo">ANTONINA/PR <span class="st st--em_andamento">Em andamento</span>')
        self.assertContains(r, f'id="termo-{cancelado.pk}-titulo">ANTONINA/PR <span class="st st--cancelada">Cancelado</span>')
        self.assertContains(r, "tm-linha--cancelada")
        # O período saiu do título e virou fato do cartão.
        self.assertContains(r, f"{self.data(3):%d/%m/%Y} a {self.data(4):%d/%m/%Y}")
        self.assertContains(r, f"{self.data(-1):%d/%m/%Y} a {self.data(1):%d/%m/%Y}")

    def test_acoes_do_cartao(self):
        o = self.oficio(dias=3, servidores=[self.janine], viatura=self.duster)
        t = self.termo(oficio=o)
        r = self.lista()
        for texto in ["Escolher documentos para baixar", "Baixar PDF", "Todos os termos num PDF só, prontos para assinatura",
                      "Baixar DOCX", "Arquivos editáveis de todos os termos (ZIP)", "Visualizar termo genérico",
                      "Visualizar termo da viatura", "AAA-1234 DUSTER", "Todos os documentos", "Anexar termo assinado",
                      "Gere o PDF do termo primeiro", "Editar termo", "Excluir termo", 'data-confirmar="Confirmar exclusão?"']:
            self.assertContains(r, texto)
        self.assertContains(r, reverse("viagens_termos:todos_pdf", args=[t.pk]))
        self.assertContains(r, reverse("viagens_termos:lote", args=[t.pk, "docx"]))
        self.assertContains(r, reverse("viagens_termos:gerar_viatura", args=[t.pk, "pdf"]) + "?inline=1")
        self.assertContains(r, reverse("viagens_termos:editar", args=[t.pk]) + "?next=")

    def test_cartao_cancelado_nao_gera_documentos(self):
        self.termo(cidade=self.antonina, inicio=self.data(3), cancelar=True)
        r = self.lista()
        self.assertContains(r, "Termo cancelado")
        self.assertContains(r, "Reative para gerar documentos")
        self.assertNotContains(r, "Visualizar termo genérico")

    def test_anexar_assinado_quando_ja_ha_pdf(self):
        o = self.oficio(dias=3, servidores=[self.janine])
        t = self.termo(oficio=o)
        self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]))
        art = DocumentoArtefato.objects.get(termo=t, servidor=self.janine, formato="pdf")
        r = self.lista()
        self.assertContains(r, reverse("viagens_oficios:assinatura_artefato", args=[art.pk]))
        self.assertContains(r, "Enviar o PDF depois da assinatura")

    def test_busca_por_destino_oficio_protocolo_viatura_e_servidor(self):
        o = self.oficio(dias=3, protocolo="123456789", servidores=[self.janine], viatura=self.duster)
        com_oficio = self.termo(oficio=o)
        avulso = self.termo(cidade=self.curitiba, inicio=self.data(5), servidores=[self.joao])

        def ids(**params):
            return [l["termo"].pk for l in self.lista(**params).context["linhas"]]

        self.assertEqual(ids(q="Antonina"), [com_oficio.pk])
        self.assertEqual(ids(q="Curitiba"), [avulso.pk])
        self.assertEqual(ids(q=o.numero_formatado), [com_oficio.pk])
        self.assertEqual(ids(q="12.345.678-9"), [com_oficio.pk])
        self.assertEqual(ids(q="AAA-1234"), [com_oficio.pk])
        self.assertEqual(ids(q="Duster"), [com_oficio.pk])
        self.assertEqual(ids(q="JANINE"), [com_oficio.pk])
        self.assertEqual(ids(q="JOÃO"), [avulso.pk])
        r = self.lista(q="ZZZ")
        self.assertContains(r, "Nenhum termo encontrado com os filtros aplicados.")

    def test_situacoes_combinaveis_com_contagem(self):
        futuro = self.termo(cidade=self.antonina, inicio=self.data(3))
        atual = self.termo(cidade=self.antonina, inicio=self.data(-3), fim=self.data(-2))
        sem_periodo = self.termo(estado=self.pr)
        cancelado = self.termo(cidade=self.antonina, inicio=self.data(3), cancelar=True)
        r = self.lista()
        # Título e contagem ficam em spans separados da trilha, como nos roteiros.
        totais = {s["titulo"]: s["total"] for s in r.context["situacoes"]}
        self.assertEqual(totais, {"Todas": 4, "Que vão acontecer": 1, "Em andamento e realizados": 2, "Finalizados": 0, "Cancelados": 1})
        for rotulo in ["Que vão acontecer", "Em andamento e realizados", "Finalizados", "Cancelados"]:
            self.assertContains(r, rotulo)
        self.assertEqual(len(r.context["linhas"]), 4)

        def ids(**params):
            return sorted(l["termo"].pk for l in self.lista(**params).context["linhas"])

        self.assertEqual(ids(situacao="futuras"), [futuro.pk])
        self.assertEqual(ids(situacao="atuais"), sorted([atual.pk, sem_periodo.pk]))
        self.assertEqual(ids(situacao=["futuras", "cancelados"]), sorted([futuro.pk, cancelado.pk]))
        self.assertEqual(ids(cancelados="1"), [cancelado.pk])

    def test_leitor_so_consulta(self):
        t = self.termo(cidade=self.antonina, inicio=self.data(3))
        self.user.groups.clear()
        r = self.lista()
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Novo termo")
        self.assertNotContains(r, "Editar termo")
        self.assertContains(r, "Abrir")
        self.assertEqual(self.client.get(reverse("viagens_termos:novo")).status_code, 403)
        self.assertEqual(self.client.post(reverse("viagens_termos:gerar", args=[t.pk, 0, "pdf"])).status_code, 403)
        self.assertEqual(self.client.post(reverse("viagens_termos:acao", args=[t.pk, "excluir"])).status_code, 403)
        self.assertEqual(self.client.get(reverse("viagens_termos:editar", args=[t.pk])).status_code, 200)

    def test_item_de_navegacao(self):
        self.assertContains(self.lista(), 'aria-current="page">Termos</a>')


class FormTermoTests(CenarioTermos):
    def test_novo_tem_os_blocos(self):
        r = self.client.get(reverse("viagens_termos:novo"))
        self.assertEqual(r.status_code, 200)
        for texto in ["Novo termo", "Buscar ofício por número, protocolo, viajante ou destino",
                      "Destino e período", "UF do destino",
                      "Município do destino", "Destinos", "Adicionar destino",
                      "Servidores e viatura", "Buscar por nome, cargo ou unidade", "JANINE LACERDA DO PRADO",
                      "AGENTE DE POLÍCIA JUDICIÁRIA · ASCOM", "AAA-1234 — DUSTER", "Salvar termo"]:
            self.assertContains(r, texto)
        # O ofício é um interruptor da seção 1, no select padrão: sem ofício o
        # painel nasce fechado e o termo é avulso.
        self.assertContains(r, "Sem ofício vinculado")
        self.assertContains(r, 'data-lista-escolha="oficio"')
        self.assertNotContains(r, "interruptor--ligado")
        self.assertNotContains(r, "_campos.html")

    def test_lista_de_oficios_traz_contexto_e_busca_o_viajante(self):
        o = self.oficio(dias=3, protocolo="123456789", servidores=[self.janine])
        r = self.client.get(reverse("viagens_termos:novo"))
        self.assertContains(r, f'<input class="sr-only" type="radio" name="oficio" value="{o.pk}">')
        self.assertContains(r, f"Ofício {o.numero_formatado}")
        # A segunda linha mostra período, destino e protocolo; o viajante não
        # aparece, mas o data-busca do filtro alcança ele.
        self.assertContains(r, "ANTONINA/PR · 123456789")
        self.assertContains(r, "JANINE LACERDA DO PRADO")

    def test_cria_termo_avulso_e_volta_pelo_next(self):
        volta = reverse("viagens_termos:lista") + "?situacao=futuras"
        r = self.client.post(reverse("viagens_termos:novo"), {
            "destino_estado": self.pr.pk, "destino_cidade": self.antonina.pk,
            "data_evento_inicio": f"{self.data(3):%Y-%m-%d}", "data_evento_fim": f"{self.data(4):%Y-%m-%d}",
            "servidores": [str(self.janine.pk)], "viatura": self.duster.pk, "next": volta,
        })
        self.assertRedirects(r, volta)
        t = TermoAutorizacao.objects.get()
        self.assertEqual(t.destino_efetivo(), "Antonina/PR")
        self.assertEqual(list(t.servidores_efetivos()), [self.janine])
        self.assertEqual(t.viatura_efetiva(), self.duster)

    def test_form_invalido_lista_os_erros(self):
        r = self.client.post(reverse("viagens_termos:novo"), {"destino_estado": self.pr.pk})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Não foi possível salvar o termo")
        self.assertContains(r, "Informe o município do destino.")
        self.assertContains(r, "Informe a data ou selecione um ofício com período.")
        self.assertFalse(TermoAutorizacao.objects.exists())

    def test_editar_mostra_oficio_escolhido_e_o_que_herda(self):
        o = self.oficio(dias=3, protocolo="123456789", servidores=[self.janine], viatura=self.duster)
        t = self.termo(oficio=o)
        r = self.client.get(reverse("viagens_termos:editar", args=[t.pk]))
        self.assertContains(r, f"Termo #{t.pk}")
        self.assertContains(r, f'<input class="sr-only" type="radio" name="oficio" value="{o.pk}" checked>')
        # Com ofício, o interruptor da seção 1 abre ligado.
        self.assertContains(r, "interruptor--ligado")
        self.assertContains(r, "Vinculado a um ofício")
        self.assertContains(r, "Este termo herda do ofício: destino, período, servidores, viatura.")
        r = self.client.post(reverse("viagens_termos:editar", args=[t.pk]), {"oficio": o.pk, "viatura": "", "servidores": [str(self.janine.pk)]})
        self.assertRedirects(r, reverse("viagens_termos:lista"))
        t.refresh_from_db()
        self.assertEqual(list(t.servidores.all()), [self.janine])

    def test_adicionar_destino_mantem_os_valores(self):
        r = self.client.post(reverse("viagens_termos:novo"), {
            "acao": "adicionar_destino", "quantidade_destinos": "1", "destino_estado": self.pr.pk, "destino_cidade": self.antonina.pk,
            "extra_estado_0": self.pr.pk, "extra_cidade_0": self.curitiba.pk,
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="quantidade_destinos" value="2"')
        for nome in ["extra_estado_0", "extra_cidade_0", "extra_estado_1", "extra_cidade_1"]:
            self.assertContains(r, f'name="{nome}"')
        self.assertContains(r, 'data-depends-on="id_extra_estado_1"')
        self.assertFalse(TermoAutorizacao.objects.exists())

    def test_api_de_busca_de_oficios(self):
        o = self.oficio(dias=3, servidores=[self.janine])
        cancelado = self.oficio(dias=3, servidores=[self.janine], cancelar=True)
        dados = self.client.get(reverse("viagens_termos:api_buscar_oficios"), {"q": "JANINE"}).json()
        self.assertEqual([item["id"] for item in dados["results"]], [o.pk])
        self.assertNotIn(cancelado.pk, [item["id"] for item in dados["results"]])
        self.assertEqual(dados["limite"], 30)


class DetalheEDocumentosTests(CenarioTermos):
    def test_tela_do_termo_lista_os_documentos(self):
        o = self.oficio(dias=-20, protocolo="123456789", servidores=[self.janine, self.joao], viatura=self.duster)
        t = self.termo(oficio=o)
        r = self.client.get(reverse("viagens_termos:editar", args=[t.pk]))
        for texto in [f"Termo #{t.pk}", "Realizado", "Destino e período", "Servidores e viatura", f"Ofício {o.numero_formatado}", "herda do ofício",
                      "Escolher documentos para baixar", "Termo por servidor", "JANINE LACERDA DO PRADO", "JOÃO MARIO DE GOES",
                      "Visualizar", "Anexar assinado", "Termo genérico", "Só destino e período, semipreenchido",
                      "Termo da viatura", "AAA-1234 DUSTER, campos do servidor em branco", "Todos os termos", "2 servidores",
                      "PDF único", "ZIP de PDFs", "ZIP de DOCX", "Documentos gerados", "Nenhum documento gerado.",
                      "Prévia em tela", "Abrir prévia", "Salvar termo"]:
            self.assertContains(r, texto)
        self.assertContains(r, reverse("viagens_termos:preview", args=[t.pk]))
        self.assertContains(r, reverse("viagens_termos:todos_pdf", args=[t.pk]))
        self.assertContains(r, reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]) + "?inline=1")

    def test_gera_por_servidor_generico_viatura_consolidado_e_zip(self):
        from pypdf import PdfReader
        o = self.oficio(dias=3, servidores=[self.janine, self.joao], viatura=self.duster)
        t = self.termo(oficio=o)
        r = self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]) + "?inline=1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.conteudo(r).startswith(b"%PDF"))
        self.assertIn("inline", r["Content-Disposition"])
        r = self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "docx"]))
        self.assertTrue(self.conteudo(r).startswith(b"PK"))
        self.assertIn("attachment", r["Content-Disposition"])

        r = self.client.post(reverse("viagens_termos:gerar", args=[t.pk, 0, "pdf"]))
        self.assertTrue(self.conteudo(r).startswith(b"%PDF"))
        generico = DocumentoArtefato.objects.get(termo=t, servidor__isnull=True, formato="pdf")
        self.assertEqual(generico.payload_snapshot["termo"]["variante"], VarianteTermo.SEMIPREENCHIDO)

        r = self.client.post(reverse("viagens_termos:gerar_viatura", args=[t.pk, "pdf"]))
        self.assertTrue(self.conteudo(r).startswith(b"%PDF"))
        viatura = DocumentoArtefato.objects.filter(termo=t, servidor__isnull=True, formato="pdf").exclude(pk=generico.pk).get()
        self.assertEqual(viatura.payload_snapshot["termo"]["variante"], VarianteTermo.COMPLETO_COM_VIATURA)
        self.assertEqual(viatura.payload_snapshot["termo"]["transporte"]["placa"], "AAA-1234")

        r = self.client.post(reverse("viagens_termos:todos_pdf", args=[t.pk]))
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertEqual(r["Content-Disposition"], f'attachment; filename="termo-{t.pk}-todos.pdf"')
        paginas = [len(PdfReader(io.BytesIO(a.arquivo.read())).pages) for a in DocumentoArtefato.objects.filter(termo=t, servidor__isnull=False, formato="pdf")]
        self.assertEqual(len(paginas), 2)
        self.assertEqual(len(PdfReader(io.BytesIO(r.content)).pages), sum(paginas))

        for formato, assinatura in [("pdf", b"%PDF"), ("docx", b"PK")]:
            r = self.client.post(reverse("viagens_termos:lote", args=[t.pk, formato]))
            self.assertEqual(r["Content-Type"], "application/zip")
            with ZipFile(io.BytesIO(r.content)) as z:
                nomes = z.namelist()
                self.assertEqual(len(nomes), 2)
                self.assertTrue(all(z.read(n).startswith(assinatura) for n in nomes))

        r = self.client.get(reverse("viagens_termos:editar", args=[t.pk]))
        self.assertNotContains(r, "Nenhum documento gerado.")
        self.assertContains(r, "JANINE LACERDA DO PRADO")

    def test_termo_cancelado_nao_gera(self):
        t = self.termo(cidade=self.antonina, inicio=self.data(3), servidores=[self.janine], cancelar=True)
        r = self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "pdf"]), follow=True)
        self.assertRedirects(r, reverse("viagens_termos:editar", args=[t.pk]))
        self.assertContains(r, "Reative o termo e o ofício antes de gerar documentos.")
        self.assertFalse(DocumentoArtefato.objects.filter(termo=t).exists())
        self.assertEqual(self.client.post(reverse("viagens_termos:gerar", args=[t.pk, self.janine.pk, "txt"])).status_code, 404)

    def test_previa_em_tela(self):
        o = self.oficio(dias=3, servidores=[self.janine, self.joao], viatura=self.duster)
        t = self.termo(oficio=o)
        r = self.client.get(reverse("viagens_termos:preview", args=[t.pk]))
        self.assertContains(r, f"Prévia do termo #{t.pk}")
        self.assertContains(r, "Com viatura")
        self.assertContains(r, "JANINE LACERDA DO PRADO")
        self.assertContains(r, "TERMO DE AUTORIZACAO")
        self.assertContains(r, f"<dt>Ofício</dt><dd>{o.numero_formatado}<small>Protocolo")
        self.assertContains(r, "Prévia por servidor")
        r = self.client.get(reverse("viagens_termos:preview_servidor", args=[t.pk, self.joao.pk]))
        self.assertContains(r, "JOÃO MARIO DE GOES")
        avulso = self.termo(cidade=self.antonina, inicio=self.data(3), servidores=[self.janine])
        r = self.client.get(reverse("viagens_termos:preview", args=[avulso.pk]))
        self.assertContains(r, "Sem viatura")
        self.assertContains(r, "Termo avulso")

    def test_acoes_cancelar_reativar_excluir(self):
        t = self.termo(cidade=self.antonina, inicio=self.data(3), servidores=[self.janine])
        detalhe = reverse("viagens_termos:editar", args=[t.pk])
        r = self.client.post(reverse("viagens_termos:acao", args=[t.pk, "cancelar"]), {"motivo": "Evento adiado"})
        self.assertRedirects(r, detalhe)
        t.refresh_from_db()
        self.assertTrue(t.cancelado)
        r = self.client.get(detalhe)
        self.assertContains(r, "Termo cancelado")
        self.assertContains(r, "Evento adiado")
        self.assertNotContains(r, "Reativar termo")  # a seção de cancelamento saiu da tela
        r = self.client.post(reverse("viagens_termos:acao", args=[t.pk, "reativar"]))
        self.assertRedirects(r, detalhe)
        t.refresh_from_db()
        self.assertFalse(t.cancelado)
        self.assertEqual(self.client.post(reverse("viagens_termos:acao", args=[t.pk, "outra"])).status_code, 404)
        volta = reverse("viagens_termos:lista") + "?q=x"
        r = self.client.post(reverse("viagens_termos:acao", args=[t.pk, "excluir"]), {"next": volta})
        self.assertRedirects(r, volta)
        self.assertFalse(TermoAutorizacao.objects.filter(pk=t.pk).exists())
