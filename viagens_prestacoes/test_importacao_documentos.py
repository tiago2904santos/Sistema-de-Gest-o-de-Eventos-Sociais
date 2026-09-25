"""Importador do processo do eProtocolo: ofício, justificativa, termos e OS nos documentos deles.

O mesmo importador da prestação, agora também nas listas de Ofícios e de Termos:
o ofício assinado vai para a prestação e para a versão assinada do documento do
ofício; justificativa, termos (um por servidor) e ordem de serviço, para a versão
assinada do documento deles — gerando antes o PDF que ainda não existia. PDF com
vários termos, sem a moldura do eProtocolo, é separado e distribuído.

PDFs sintéticos (`core.leitura.tests.fabrica`); nenhum processo real entra aqui.
OCR desligado: o resultado não pode depender do tesseract da máquina.
"""

from __future__ import annotations

from datetime import date
from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from core.leitura.tests import fabrica as f
from documentos.models import DocumentoArtefato
from documentos.models import DocumentoAssinaturaVersao
from documentos.services.assinados import versao_assinada_vigente
from documentos.services.filenames import build_document_filename
from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo
from viagens_oficios.models import Oficio
from viagens_ordens.models import OrdemServico
from viagens_termos.models import TermoAutorizacao

from .importacao.plano import DESTINO_TERMO
from .importacao.plano import Plano
from .models import ImportacaoProcesso
from .models import PrestacaoDocumentoAnexo as Anexo
from .test_importacao import PROTOCOLO
from .test_importacao import ImportacaoBase
from .test_importacao import _mensagens

CHEFE = ("Chefe da Silva", "11144477735")


def _conteudo(campo) -> bytes:
    campo.open("rb")
    try:
        return campo.read()
    finally:
        campo.close()


def _texto(pdf: bytes) -> str:
    return " ".join(" ".join((p.extract_text() or "").split()) for p in PdfReader(BytesIO(pdf)).pages)


def _arquivos() -> set[str]:
    raiz = Path(settings.MEDIA_ROOT)
    return {str(p.relative_to(raiz)).replace("\\", "/") for p in raiz.rglob("*") if p.is_file()}


@override_settings(DOCUMENTOS_DEFAULT_PDF_ENGINE="simple")
class DocumentosBase(ImportacaoBase):
    """Ofício 12/2026 (viagem em 20/09/2026) com termo para FULANO e BELTRANA; CICRANO viaja sem termo."""

    def setUp(self):
        super().setUp()
        self.fulano, self.beltrana, self.cicrano = self.servidores
        self.oficio.servidores_termo_autorizacao.set([self.fulano, self.beltrana])
        roteiro = self.fixture.roteiro
        roteiro.saida_dt = timezone.make_aware(datetime(2026, 9, 20, 7, 0))
        roteiro.retorno_chegada_dt = timezone.make_aware(datetime(2026, 9, 20, 19, 0))
        roteiro.save()

    # -- PDFs -----------------------------------------------------------------
    def termo(self, servidor, *, data="no dia 20 de setembro de 2026") -> bytes:
        return f.termo_autorizacao(nome=servidor.nome, cpf=servidor.cpf, data_evento=data)

    def processo_autorizacao(self, *, termos=None, com_os=False, despacho=True) -> bytes:
        """Ofício + justificativa + um termo por servidor (+ OS) + despacho, como volta do eProtocolo."""
        docs = [
            f.Doc(f.oficio_viagens(numero=12, ano=2026, protocolo=PROTOCOLO, servidores=self.equipe(3)),
                  arquivo="Of.12-2026.pdf", assinantes=[CHEFE], embrulhar=True),
            f.Doc(f.justificativa(), arquivo="Justificativa.pdf", assinantes=[CHEFE]),
        ]
        for servidor in (termos if termos is not None else [self.fulano, self.beltrana]):
            docs.append(f.Doc(self.termo(servidor), arquivo=f"Termo_{servidor.nome.split()[0]}.pdf",
                              assinantes=[(servidor.nome.title(), servidor.cpf)]))
        if com_os:
            docs.append(f.Doc(f.ordem_servico(numero=5, ano=2026), arquivo="OS_05-2026.pdf", assinantes=[CHEFE]))
        if despacho:
            docs.append(f.Doc(f.despacho(protocolo=PROTOCOLO), arquivo="DESPACHO_1.pdf", assinantes=[CHEFE]))
        return f.processo_eprotocolo(docs, protocolo=PROTOCOLO, numero_ano="12/2026")

    # -- envio ----------------------------------------------------------------
    def enviar_para(self, rota, pdf, *args, origem="", nome="Processo_26.613.666-8_1.pdf", **extra):
        dados = {"arquivo": SimpleUploadedFile(nome, pdf, content_type="application/pdf"), **extra}
        if origem:
            dados["origem"] = origem
        return self.client.post(reverse(f"viagens_prestacoes:{rota}", args=args), dados)

    # -- documentos gerados ---------------------------------------------------
    def artefato_gerado(self, tipo: DocumentoTipo, referencia: str, **vinculos) -> DocumentoArtefato:
        """Um PDF "gerado antes" (sem passar pelo motor), com o nome que a geração daria."""
        artefato = DocumentoArtefato(
            tipo=tipo.value, formato="pdf", nome_exibicao=build_document_filename(tipo, DocumentoFormato.PDF, reference=referencia),
            hash_sha256="0" * 64, **vinculos,
        )
        artefato.arquivo.save("gerado.pdf", ContentFile(f.pagina([f"GERADO {tipo.value}"])), save=False)
        artefato.save()
        return artefato

    def assinado(self, tipo: DocumentoTipo, referencia: str, **vinculos) -> bytes | None:
        arquivo = versao_assinada_vigente(tipo, reference=referencia, **vinculos)
        return _conteudo(arquivo) if arquivo else None

    def termo_do_oficio_assinado(self, servidor) -> bytes | None:
        return self.assinado(DocumentoTipo.TERMO_AUTORIZACAO, f"12-2026-termo-{servidor.pk}",
                             oficio_id=self.oficio.pk, servidor_id=servidor.pk)

    def termo_do_cadastro_assinado(self, termo, servidor) -> bytes | None:
        return self.assinado(DocumentoTipo.TERMO_AUTORIZACAO, f"termo-{termo.pk}-cadastro-{servidor.pk}",
                             oficio_id=termo.oficio_id, termo_id=termo.pk, servidor_id=servidor.pk)


class PelaListaDeOficiosTests(DocumentosBase):
    def test_processo_da_autorizacao_vai_para_o_oficio_a_justificativa_os_termos_e_a_prestacao(self):
        oficio_pdf = self.artefato_gerado(DocumentoTipo.OFICIO, "12-2026", oficio=self.oficio)
        justificativa_pdf = self.artefato_gerado(DocumentoTipo.JUSTIFICATIVA, "12-2026", oficio=self.oficio)
        resposta = self.enviar_para(
            "importacao_enviar_oficio", self.processo_autorizacao(), self.oficio.pk,
            origem="oficios", next=reverse("viagens_oficios:lista"),
        )

        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA, importacao.plano)
        self.assertRedirects(
            resposta,
            reverse("viagens_prestacoes:importacao_detalhe", args=[importacao.pk]) + "?next=" + reverse("viagens_oficios:lista").replace("/", "%2F"),
            fetch_redirect_response=False,
        )
        plano = Plano.de_json(importacao.plano)
        self.assertEqual(plano.origem, "oficios")
        self.assertEqual(plano.evidencias[0], "ofício escolhido na lista")

        # Na prestação: o ofício (com a folha de assinatura) e o despacho.
        self.assertEqual(len(self.anexos(Anexo.TIPO_OFICIO_ASSINADO)), 1)
        self.assertEqual(len(self.anexos(Anexo.TIPO_DESPACHO)), 1)

        # O ofício assinado também é a versão assinada do documento do ofício — sem o carimbo da prestação.
        versao = oficio_pdf.versoes_assinadas.get()
        texto = _texto(_conteudo(versao.arquivo))
        self.assertIn("Ofício Nº 12/2026", texto)
        self.assertIn("Documento: Of.12-2026.pdf", texto)  # a folha "Na" vai junto
        self.assertEqual(versao.nome_original, "Of.12-2026.pdf")
        oficio_pdf.refresh_from_db()
        self.assertTrue(oficio_pdf.esta_assinado)
        self.assertIn("Justificativa", _texto(_conteudo(justificativa_pdf.versoes_assinadas.get().arquivo)))

        # Os termos: sem PDF gerado, o sistema gera e anexa o assinado de cada um no dele.
        for servidor, outro in ((self.fulano, self.beltrana), (self.beltrana, self.fulano)):
            texto = _texto(self.termo_do_oficio_assinado(servidor))
            self.assertIn(servidor.nome, texto)
            self.assertNotIn(outro.nome, texto)
        self.assertIsNone(self.termo_do_oficio_assinado(self.cicrano))

        # A geração passa a entregar o assinado (Visualizar, Baixar documentos).
        from viagens_termos.services import gerar_termo_um

        self.assertEqual(gerar_termo_um(self.oficio, self.fulano, DocumentoFormato.PDF).conteudo, self.termo_do_oficio_assinado(self.fulano))

        resultado = importacao.resultado
        self.assertEqual(
            resultado["resumo_documentos"],
            f"Versões assinadas anexadas: ofício, justificativa, termos de {self.fulano.nome} e {self.beltrana.nome}.",
        )
        self.assertIn(resultado["resumo_documentos"], _mensagens(resposta))
        self.assertEqual({d["alvo"] for d in resultado["documentos"] if d["gerado"]},
                         {f"Termo de {self.fulano.nome} · Ofício 12/2026", f"Termo de {self.beltrana.nome} · Ofício 12/2026"})

    def test_termo_do_cadastro_preso_ao_oficio_tambem_recebe(self):
        termo = TermoAutorizacao.objects.create(oficio=self.oficio)
        self.enviar_para("importacao_enviar_oficio", self.processo_autorizacao(termos=[self.fulano]), self.oficio.pk, origem="oficios")
        self.assertEqual(self.importacao().situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        self.assertIn(self.fulano.nome, _texto(self.termo_do_cadastro_assinado(termo, self.fulano)))
        self.assertIsNotNone(self.termo_do_oficio_assinado(self.fulano))

    def test_termo_de_quem_nao_esta_marcado_para_termo_vai_para_a_conferencia(self):
        self.enviar_para("importacao_enviar_oficio", self.processo_autorizacao(termos=[self.cicrano]), self.oficio.pk, origem="oficios")
        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        item = next(i for i in Plano.de_json(importacao.plano).itens if i.destino == DESTINO_TERMO)
        self.assertIsNone(item.servidor_id)
        self.assertIn(f"{self.cicrano.nome} não está marcado para termo no Ofício 12/2026", " ".join(item.conferir))
        self.assertFalse(DocumentoAssinaturaVersao.objects.exists())
        self.assertFalse(self.prestacao.documentos_anexos.exists())

        # Deixar o termo de fora e aplicar: o resto entra.
        self.client.post(reverse("viagens_prestacoes:importacao_aplicar", args=[importacao.pk]), {
            "prestacao": str(self.prestacao.pk), "acao": "aplicar", f"doc-{item.ordem}-destino": "ignorar",
        })
        importacao.refresh_from_db()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        self.assertEqual(len(self.anexos(Anexo.TIPO_DESPACHO)), 1)

    def test_ordem_de_servico_do_oficio_recebe_o_assinado(self):
        ordem = OrdemServico.objects.create(numero=5, ano=2026)
        ordem.oficios.add(self.oficio)
        pdf_os = self.artefato_gerado(DocumentoTipo.ORDEM_SERVICO, "os-005-2026", ordem_servico=ordem)
        self.enviar_para("importacao_enviar_oficio", self.processo_autorizacao(termos=[], com_os=True), self.oficio.pk, origem="oficios")
        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA, importacao.plano)
        self.assertIn("Ordem de Serviço 05/2026", _texto(_conteudo(pdf_os.versoes_assinadas.get().arquivo)))
        self.assertIn("Ordem de Serviço 05/2026", importacao.resultado["resumo_documentos"])

    def test_os_que_nao_e_de_viagens_fica_de_fora(self):
        self.enviar_para("importacao_enviar_oficio", self.processo_autorizacao(termos=[], com_os=True), self.oficio.pk, origem="oficios")
        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        item = next(i for i in Plano.de_json(importacao.plano).itens if i.tipo_lido == "ordem_servico")
        self.assertEqual(item.destino, "ignorar")
        self.assertIn("não está cadastrada em Viagens", item.motivo)

    def test_termo_que_nao_da_para_gerar_vira_aviso_e_o_resto_entra(self):
        from documentos.services.exceptions import DocumentError

        with mock.patch("viagens_termos.services.gerar_termo_um", side_effect=DocumentError("motor de PDF indisponível")):
            self.enviar_para("importacao_enviar_oficio", self.processo_autorizacao(termos=[self.fulano]), self.oficio.pk, origem="oficios")
        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        self.assertTrue(any("não há PDF gerado, e não deu para gerar agora (motor de PDF indisponível)" in a for a in importacao.resultado["avisos"]))
        self.assertFalse(DocumentoArtefato.objects.filter(tipo=DocumentoTipo.TERMO_AUTORIZACAO.value).exists())
        self.assertEqual(len(self.anexos(Anexo.TIPO_DESPACHO)), 1)

    def test_aplicar_de_novo_nao_repete_a_versao(self):
        oficio_pdf = self.artefato_gerado(DocumentoTipo.OFICIO, "12-2026", oficio=self.oficio)
        self.enviar_para("importacao_enviar_oficio", self.processo_autorizacao(), self.oficio.pk, origem="oficios")
        importacao = self.importacao()
        versoes = DocumentoAssinaturaVersao.objects.count()
        resposta = self.client.post(reverse("viagens_prestacoes:importacao_aplicar", args=[importacao.pk]), {"acao": "aplicar"})
        self.assertEqual(DocumentoAssinaturaVersao.objects.count(), versoes)
        self.assertEqual(oficio_pdf.versoes_assinadas.count(), 1)
        importacao.refresh_from_db()
        self.assertIn("Já estavam anexados: ofício", importacao.resultado["resumo_documentos"])
        self.assertTrue(any("Já estavam anexados" in m for m in _mensagens(resposta)))


class PelaListaDeTermosTests(DocumentosBase):
    def test_pdf_com_varios_termos_sem_moldura_e_separado_e_distribuido(self):
        termo = TermoAutorizacao.objects.create(oficio=self.oficio)
        pdf = f.juntar(self.termo(self.beltrana), self.termo(self.fulano))  # escaneados juntos, sem o eProtocolo
        resposta = self.enviar_para("importacao_enviar_termo", pdf, termo.pk, origem="termos", nome="termos.pdf")

        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA, importacao.plano)
        plano = Plano.de_json(importacao.plano)
        self.assertEqual((plano.termo_id, plano.prestacao_id, plano.origem), (termo.pk, self.prestacao.pk, "termos"))
        self.assertEqual([i.servidor_id for i in plano.itens], [self.beltrana.pk, self.fulano.pk])
        for servidor, outro in ((self.fulano, self.beltrana), (self.beltrana, self.fulano)):
            for conteudo in (self.termo_do_cadastro_assinado(termo, servidor), self.termo_do_oficio_assinado(servidor)):
                self.assertIn(servidor.nome, _texto(conteudo))
                self.assertNotIn(outro.nome, _texto(conteudo))
                self.assertEqual(len(PdfReader(BytesIO(conteudo)).pages), 1)
        # Só termos: nada na prestação.
        self.assertFalse(self.prestacao.documentos_anexos.exists())
        self.assertEqual(
            importacao.resultado["resumo"],
            f"Arquivo importado. Versões assinadas anexadas: termos de {self.beltrana.nome} e {self.fulano.nome}.",
        )

        # A conferência/resultado volta para a lista de Termos.
        tela = self.client.get(resposta.url)
        self.assertContains(tela, f'href="{reverse("viagens_termos:lista")}">Termos de Autorização</a>')
        self.assertContains(tela, "Ver o assinado")
        self.assertContains(tela, f"Termo #{termo.pk} de {self.fulano.nome}")

    def test_termo_avulso_achado_pelos_servidores_e_pela_data(self):
        termo = TermoAutorizacao.objects.create(data_evento_inicio=date(2026, 10, 5), data_evento_fim=date(2026, 10, 5))
        termo.servidores.set([self.cicrano])
        pdf = self.termo(self.cicrano, data="no dia 5 de outubro de 2026")
        self.enviar_para("importacao_enviar", pdf, origem="termos", nome="termo_cicrano.pdf")

        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA, importacao.plano)
        plano = Plano.de_json(importacao.plano)
        self.assertEqual((plano.termo_id, plano.prestacao_id, plano.camada), (termo.pk, None, "termos"))
        self.assertIn(self.cicrano.nome, _texto(self.termo_do_cadastro_assinado(termo, self.cicrano)))
        self.assertIsNone(importacao.prestacao)
        self.assertFalse(self.prestacao.documentos_anexos.exists())

    def test_pdf_so_de_termos_acha_a_viagem_pela_equipe_e_pela_data(self):
        pdf = f.juntar(self.termo(self.fulano), self.termo(self.beltrana))
        self.enviar_para("importacao_enviar", pdf, origem="termos", nome="termos.pdf")
        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA, importacao.plano)
        plano = Plano.de_json(importacao.plano)
        self.assertEqual((plano.prestacao_id, plano.camada), (self.prestacao.pk, "termos"))
        self.assertIsNotNone(self.termo_do_oficio_assinado(self.beltrana))

    def test_mesmos_servidores_em_outra_data_nao_aplica_sozinho(self):
        pdf = self.termo(self.fulano, data="no dia 3 de março de 2026")
        self.enviar_para("importacao_enviar", pdf, origem="termos", nome="termo.pdf")
        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        self.assertFalse(DocumentoAssinaturaVersao.objects.exists())

    def test_termos_so_de_imagem_propoe_o_servidor_na_ordem_de_impressao(self):
        termo = TermoAutorizacao.objects.create(oficio=self.oficio)
        # Impressos juntos, na ordem do sistema (por nome), e escaneados: só imagem, sem OCR.
        pdf = f.juntar(f.pagina_imagem(self.termo(self.beltrana)), f.pagina_imagem(self.termo(self.fulano)))
        self.enviar_para("importacao_enviar_termo", pdf, termo.pk, origem="termos", nome="escaneados.pdf")

        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        plano = Plano.de_json(importacao.plano)
        self.assertEqual([i.destino for i in plano.itens], [DESTINO_TERMO, DESTINO_TERMO])
        self.assertEqual([i.servidor_id for i in plano.itens], [self.beltrana.pk, self.fulano.pk])
        self.assertTrue(all("confira de quem é" in " ".join(i.conferir) for i in plano.itens))
        tela = self.client.get(reverse("viagens_prestacoes:importacao_detalhe", args=[importacao.pk]))
        self.assertContains(tela, 'name="doc-1-termo_servidor"')

        # Na conferência, confirma (e troca, se preciso): um clique em "Aplicar".
        self.client.post(reverse("viagens_prestacoes:importacao_aplicar", args=[importacao.pk]), {
            "prestacao": str(self.prestacao.pk), "acao": "aplicar",
            "doc-1-destino": DESTINO_TERMO, "doc-1-termo_servidor": str(self.beltrana.pk),
            "doc-2-destino": DESTINO_TERMO, "doc-2-termo_servidor": str(self.fulano.pk),
        })
        importacao.refresh_from_db()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        self.assertIsNotNone(self.termo_do_cadastro_assinado(termo, self.beltrana))
        self.assertIsNotNone(self.termo_do_oficio_assinado(self.fulano))

    def test_servidor_de_fora_do_termo_na_conferencia_e_recusado(self):
        termo = TermoAutorizacao.objects.create(oficio=self.oficio)
        pdf = f.pagina_imagem(self.termo(self.fulano))
        self.enviar_para("importacao_enviar_termo", pdf, termo.pk, origem="termos", nome="escaneado.pdf")
        importacao = self.importacao()
        self.client.post(reverse("viagens_prestacoes:importacao_aplicar", args=[importacao.pk]), {
            "prestacao": str(self.prestacao.pk), "acao": "aplicar",
            "doc-1-destino": DESTINO_TERMO, "doc-1-termo_servidor": str(self.cicrano.pk),
        })
        importacao.refresh_from_db()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        self.assertFalse(DocumentoAssinaturaVersao.objects.exists())

    def test_termo_cancelado_recusa(self):
        termo = TermoAutorizacao.objects.create(oficio=self.oficio)
        termo.cancelar("Adiado")
        resposta = self.enviar_para("importacao_enviar_termo", self.termo(self.fulano), termo.pk, origem="termos")
        self.assertFalse(ImportacaoProcesso.objects.exists())
        self.assertIn("Este termo está cancelado.", _mensagens(resposta))


class TudoOuNadaTests(DocumentosBase):
    def test_falha_no_meio_desfaz_anexos_versoes_gerados_e_arquivos(self):
        oficio_pdf = self.artefato_gerado(DocumentoTipo.OFICIO, "12-2026", oficio=self.oficio)
        from documentos.services import persistence

        real = persistence.anexar_arquivo_assinado
        chamadas = []

        def quebra_no_terceiro(*args, **kwargs):
            chamadas.append(1)
            if len(chamadas) == 3:
                raise RuntimeError("disco cheio")
            return real(*args, **kwargs)

        from .importacao import aplicar_importacao
        from .importacao import registrar_importacao
        from .importacao.analise import analisar

        pdf = self.processo_autorizacao()
        plano = analisar(pdf, "Processo.pdf", prestacao=self.prestacao, origem="oficios")
        self.assertTrue(plano.pronto, plano.pendencias)
        importacao = registrar_importacao(pdf, "Processo.pdf", plano)
        antes = _arquivos()
        with mock.patch.object(persistence, "anexar_arquivo_assinado", side_effect=quebra_no_terceiro):
            with self.assertRaises(RuntimeError):
                aplicar_importacao(importacao)

        self.assertEqual(len(chamadas), 3)
        self.assertFalse(DocumentoAssinaturaVersao.objects.exists())
        self.assertEqual(list(DocumentoArtefato.objects.all()), [oficio_pdf])  # os termos gerados saíram junto
        oficio_pdf.refresh_from_db()
        self.assertFalse(oficio_pdf.arquivo_assinado)
        self.assertFalse(self.prestacao.documentos_anexos.exists())
        importacao.refresh_from_db()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        self.assertEqual(_arquivos(), antes)


class TelasTests(DocumentosBase):
    def test_lista_de_oficios_tem_o_importador(self):
        lista = self.client.get(reverse("viagens_oficios:lista"))
        self.assertContains(lista, "Importar processo do eProtocolo")
        self.assertContains(lista, reverse("viagens_prestacoes:importacao_enviar_oficio", args=[self.oficio.pk]))
        self.assertContains(lista, 'name="origem" value="oficios"')
        self.assertContains(lista, "data-importar-soltar")
        self.assertContains(lista, "js/prestacoes-importar.js")

    def test_lista_de_termos_tem_o_importador(self):
        termo = TermoAutorizacao.objects.create(oficio=self.oficio)
        lista = self.client.get(reverse("viagens_termos:lista"))
        self.assertContains(lista, "Importar processo do eProtocolo")
        self.assertContains(lista, "Importar termos assinados")
        self.assertContains(lista, reverse("viagens_prestacoes:importacao_enviar_termo", args=[termo.pk]))
        self.assertContains(lista, 'name="origem" value="termos"')

    def test_quem_so_consulta_nao_ve_o_importador(self):
        from django.contrib.auth.models import Group

        self.user.groups.remove(Group.objects.get(name="VIAGENS_OPERADOR"))
        for nome in ("viagens_oficios:lista", "viagens_termos:lista"):
            self.assertNotContains(self.client.get(reverse(nome)), "data-importar-processo")

    def test_conferencia_da_lista_de_oficios_volta_para_ela(self):
        self.enviar_para("importacao_enviar", self.processo_autorizacao(termos=[self.cicrano]), origem="oficios")
        importacao = self.importacao()
        tela = self.client.get(reverse("viagens_prestacoes:importacao_detalhe", args=[importacao.pk]))
        self.assertContains(tela, f'href="{reverse("viagens_oficios:lista")}">Ofícios</a>')
        self.assertContains(tela, f'<a class="btn--secundaria" href="{reverse("viagens_oficios:lista")}">Voltar à lista</a>')
        self.assertContains(tela, "Termo de autorização")
        self.assertContains(tela, 'data-imp-quando="termo_autorizacao"')


class OficioCanceladoTests(DocumentosBase):
    def test_oficio_cancelado_recusa(self):
        Oficio.objects.filter(pk=self.oficio.pk).update(cancelado=True)
        resposta = self.enviar_para("importacao_enviar_oficio", self.processo_autorizacao(), self.oficio.pk, origem="oficios")
        self.assertFalse(ImportacaoProcesso.objects.exists())
        self.assertIn("Este ofício está cancelado.", _mensagens(resposta))


class ServidorDoTermoTests(DocumentosBase):
    """De quem é o termo: CPF completo, depois RG, depois o nome — só entre quem tem termo na viagem."""

    def doc(self, **dados):
        from types import SimpleNamespace

        return SimpleNamespace(dados=dados)

    def test_cpf_rg_e_nome(self):
        from .importacao.documentos import servidor_do_termo

        self.beltrana.rg = "123456789"
        self.beltrana.save(update_fields=["rg"])
        equipe = [self.fulano, self.beltrana]
        self.assertEqual(servidor_do_termo(self.doc(cpf=self.fulano.cpf), equipe)[0], self.fulano)
        achado, evidencias = servidor_do_termo(self.doc(rg="12.345.678-9"), equipe)
        self.assertEqual(achado, self.beltrana)
        self.assertEqual(evidencias, [f"RG do termo confere com {self.beltrana.nome}"])
        self.assertEqual(servidor_do_termo(self.doc(nome="Fulano de Tal"), equipe)[0], self.fulano)
        # CPF de quem não tem termo nesta viagem: ninguém (a conferência pergunta).
        self.assertIsNone(servidor_do_termo(self.doc(cpf=self.cicrano.cpf, nome=self.cicrano.nome), equipe)[0])
