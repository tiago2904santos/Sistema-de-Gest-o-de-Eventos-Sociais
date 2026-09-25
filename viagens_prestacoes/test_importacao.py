"""Importador do processo do eProtocolo na prestação de contas.

Os PDFs são sintéticos (`core.leitura.tests.fabrica`): imitam a moldura do
eProtocolo — capa, marcadores, rodapé "Inserido ao protocolo … código", carimbo
Fls./Mov., folha de assinatura "Na", página embrulhada com o Y invertido — e o
texto que o próprio sistema imprime (ofício, RT, diário deitado) e os bancos
(comprovantes). Nenhum processo real entra no repositório.

O OCR fica desligado (`OCR_ATIVO=False`): o resultado não pode depender de o
tesseract estar instalado na máquina que roda os testes.
"""

from __future__ import annotations

from datetime import date
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from core.leitura.pdf import ler_paginas
from core.leitura.pdf import rotacao_para_ficar_em_pe
from core.leitura.tests import fabrica as f
from viagens_cadastros.models import Cargo
from viagens_cadastros.models import Servidor
from viagens_oficios.models import Oficio

from .importacao import aplicar_importacao
from .importacao import analisar
from .importacao import registrar_importacao
from .importacao.plano import Plano
from .models import ImportacaoProcesso
from .models import PrestacaoDocumentoAnexo as Anexo
from .test_helpers import PrestacaoFixturesMixin
from .test_helpers import PrestacaoTestCase as TestCase
from .test_helpers import pdf_minimo

PROTOCOLO = "26.613.666-8"
PROTOCOLO_DIGITOS = "266136668"
NOMES = ("FULANO DE TAL", "BELTRANA SOUZA", "CICRANO PEREIRA")


def _bytes(campo) -> bytes:
    campo.open("rb")
    try:
        return campo.read()
    finally:
        campo.close()


def _textos(pdf: bytes) -> list[str]:
    return [" ".join((p.extract_text() or "").split()) for p in PdfReader(BytesIO(pdf)).pages]


def _mensagens(resposta) -> list[str]:
    return [str(m) for m in get_messages(resposta.wsgi_request)]


@override_settings(OCR_ATIVO=False)
class ImportacaoBase(PrestacaoFixturesMixin, TestCase):
    """Uma prestação do Ofício 12/2026 com três servidores de CPF conhecido."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        cargo, _ = Cargo.objects.get_or_create(nome="AGENTE")
        self.cpfs = [f.gerar_cpf(semente) for semente in (11, 12, 13)]
        self.servidores = [Servidor.objects.create(nome=nome, cargo=cargo, cpf=cpf) for nome, cpf in zip(NOMES, self.cpfs)]
        self.fixture = self.criar_prestacao(numero=12, ano=2026, servidores=self.servidores)
        self.prestacao = self.fixture.prestacao
        self.oficio = self.fixture.oficio
        self.ps = {ps.servidor.nome: ps for ps in self.fixture.prestacoes_servidor}
        self.definir_protocolo(PROTOCOLO_DIGITOS, Oficio.PROTOCOLO_ORIGEM_MANUAL)

    def definir_protocolo(self, numero, origem):
        Oficio.objects.filter(pk=self.oficio.pk).update(protocolo=numero, protocolo_origem=origem)
        self.oficio.refresh_from_db()

    def equipe(self, quantos=3):
        return list(zip(NOMES, self.cpfs))[:quantos]

    def processo(self, *, quantos=1, protocolo=PROTOCOLO, numero_ano="12/2026"):
        """Ofício 12/2026 + despacho + RT de cada um, com a capa dizendo `numero_ano`."""
        docs = [
            f.Doc(f.oficio_viagens(numero=12, ano=2026, protocolo=protocolo, servidores=self.equipe(quantos)),
                  arquivo="Of.12-2026.pdf", assinantes=[("Chefe da Silva", "11144477735")], embrulhar=True),
            f.Doc(f.despacho(protocolo=protocolo), arquivo="DESPACHO_1.pdf"),
        ]
        for nome, cpf in self.equipe(quantos):
            docs.append(f.Doc(f.relatorio_tecnico(oficio="12/2026", nome=nome, cpf=cpf), arquivo=f"RT_{nome.split()[0]}.pdf"))
        return f.processo_eprotocolo(docs, protocolo=protocolo, numero_ano=numero_ano)

    def enviar(self, pdf, *, nome="Processo_26.613.666-8_1.pdf", prestacao=None, seguir=False):
        url = (
            reverse("viagens_prestacoes:importacao_enviar_prestacao", args=[prestacao.pk])
            if prestacao else reverse("viagens_prestacoes:importacao_enviar")
        )
        return self.client.post(url, {"arquivo": SimpleUploadedFile(nome, pdf, content_type="application/pdf")}, follow=seguir)

    def anexos(self, tipo, ps=None):
        qs = self.prestacao.documentos_anexos.filter(tipo=tipo)
        if ps is not None:
            qs = qs.filter(servidor_prestacao=ps)
        return list(qs.order_by("criado_em", "pk"))

    def importacao(self):
        return ImportacaoProcesso.objects.latest("pk")


class IdentificacaoTests(ImportacaoBase):
    def test_pelo_protocolo_aplica_sozinho_e_resume_o_que_entrou(self):
        pdf = f.processo_viagens(servidores=self.equipe(), modelos_comprovante=("bb_pix", "bradesco_transferencia", "caixa_saque"))
        resposta = self.enviar(pdf)

        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        self.assertRedirects(resposta, reverse("viagens_prestacoes:importacao_detalhe", args=[importacao.pk]), fetch_redirect_response=False)
        self.assertEqual(importacao.prestacao, self.prestacao)
        self.assertEqual(len(self.anexos(Anexo.TIPO_OFICIO_ASSINADO)), 1)
        self.assertEqual(len(self.anexos(Anexo.TIPO_DESPACHO)), 1)
        self.assertEqual(len(self.anexos(Anexo.TIPO_DB_ASSINADO)), 1)
        for nome in NOMES:
            self.assertEqual(len(self.anexos(Anexo.TIPO_RT_ASSINADO, self.ps[nome])), 1, nome)
            self.assertEqual(len(self.anexos(Anexo.TIPO_COMPROVANTE, self.ps[nome])), 1, nome)
        resumo = importacao.resultado["resumo"]
        self.assertEqual(
            resumo,
            "Processo 26.613.666-8 importado na prestação do Ofício 12/2026: ofício, despacho, "
            "RT de 3 servidores, diário (girado), 3 comprovantes.",
        )
        self.assertIn(resumo, _mensagens(resposta))
        # Status como nos endpoints: compartilhado marca a equipe; nada é finalizado.
        for ps in self.prestacao.servidores_prestacao.all():
            self.assertEqual(ps.status, ps.STATUS_EM_PREENCHIMENTO)
            self.assertFalse(ps.finalizada)
        # O anexo sabe de onde veio.
        despacho = self.anexos(Anexo.TIPO_DESPACHO)[0]
        self.assertEqual(despacho.importacao, importacao)
        self.assertEqual(despacho.paginas_origem, "4-5")

    def test_pelo_numero_do_oficio_com_protocolo_simulado_grava_o_protocolo_real(self):
        self.definir_protocolo("999999999", Oficio.PROTOCOLO_ORIGEM_SIMULADO)
        pdf = f.processo_viagens(servidores=self.equipe(2))
        self.enviar(pdf)

        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        self.assertEqual(Plano.de_json(importacao.plano).camada, "numero_ano")
        self.oficio.refresh_from_db()
        self.assertEqual(self.oficio.protocolo, PROTOCOLO_DIGITOS)
        self.assertEqual(self.oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_MANUAL)
        self.assertTrue(any("26.613.666-8" in aviso and "gravado" in aviso for aviso in importacao.resultado["avisos"]))

    def test_protocolo_oficial_de_outro_numero_nao_e_trocado(self):
        self.definir_protocolo("111111111", Oficio.PROTOCOLO_ORIGEM_MANUAL)
        self.enviar(f.processo_viagens(servidores=self.equipe(1)))
        self.oficio.refresh_from_db()
        self.assertEqual(self.oficio.protocolo, "111111111")

    def test_ambiguidade_vai_para_a_conferencia_com_os_candidatos(self):
        outro = self.criar_prestacao(numero=13, ano=2026, servidores=[self.criar_servidor("OUTRA PESSOA")])
        self.definir_protocolo("", Oficio.PROTOCOLO_ORIGEM_MANUAL)
        # A capa diz 13/2026 e o ofício dentro do processo diz 12/2026.
        pdf = self.processo(protocolo="27.000.000-1", numero_ano="13/2026")
        resposta = self.enviar(pdf)

        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        self.assertFalse(self.prestacao.documentos_anexos.exists())
        self.assertFalse(outro.prestacao.documentos_anexos.exists())
        plano = Plano.de_json(importacao.plano)
        self.assertFalse(plano.identificacao_segura)
        self.assertEqual({c.prestacao_id for c in plano.candidatos}, {self.prestacao.pk, outro.prestacao.pk})
        tela = self.client.get(resposta.url)
        self.assertContains(tela, "Ofício 12/2026")
        self.assertContains(tela, "Ofício 13/2026")
        self.assertContains(tela, 'name="prestacao"')

    def test_escolher_a_prestacao_na_conferencia_relê_e_aplica(self):
        self.criar_prestacao(numero=13, ano=2026, servidores=[self.criar_servidor("OUTRA PESSOA")])
        self.definir_protocolo("", Oficio.PROTOCOLO_ORIGEM_MANUAL)
        pdf = self.processo(protocolo="27.000.000-1", numero_ano="13/2026")
        self.enviar(pdf)
        importacao = self.importacao()
        url = reverse("viagens_prestacoes:importacao_aplicar", args=[importacao.pk])

        self.client.post(url, {"prestacao": str(self.prestacao.pk), "acao": "reanalisar"})
        importacao.refresh_from_db()
        plano = Plano.de_json(importacao.plano)
        self.assertEqual(plano.prestacao_id, self.prestacao.pk)
        rt = next(item for item in plano.itens if item.destino == Anexo.TIPO_RT_ASSINADO)
        self.assertEqual(rt.servidor_prestacao_id, self.ps[NOMES[0]].pk)

        self.client.post(url, {"prestacao": str(self.prestacao.pk), "acao": "aplicar"})
        importacao.refresh_from_db()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        self.assertEqual(len(self.anexos(Anexo.TIPO_RT_ASSINADO, self.ps[NOMES[0]])), 1)

    def test_pelo_menu_do_oficio_a_prestacao_ja_vem_escolhida(self):
        self.definir_protocolo("", Oficio.PROTOCOLO_ORIGEM_MANUAL)
        pdf = f.processo_viagens(servidores=self.equipe(1), protocolo="27.000.000-1")
        self.enviar(pdf, prestacao=self.prestacao)
        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        self.assertEqual(Plano.de_json(importacao.plano).camada, "escolhida")
        # Ofício sem protocolo recebe o do processo, como informado à mão.
        self.oficio.refresh_from_db()
        self.assertEqual((self.oficio.protocolo, self.oficio.protocolo_origem), ("270000001", Oficio.PROTOCOLO_ORIGEM_MANUAL))

    def test_pelo_menu_de_outro_oficio_desconfia_e_pede_conferencia(self):
        outro = self.criar_prestacao(numero=13, ano=2026, servidores=[self.criar_servidor("OUTRA PESSOA")])
        self.enviar(f.processo_viagens(servidores=self.equipe(1)), prestacao=outro.prestacao)
        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        self.assertTrue(any("Ofício 12/2026" in aviso for aviso in Plano.de_json(importacao.plano).avisos))
        self.assertFalse(outro.prestacao.documentos_anexos.exists())


class DocumentosTests(ImportacaoBase):
    def _importar(self, docs, **opcoes):
        pdf = f.processo_eprotocolo(docs, protocolo=PROTOCOLO, numero_ano="12/2026", **opcoes)
        self.enviar(pdf)
        return self.importacao()

    def _oficio_doc(self, quantos=1):
        return f.Doc(
            f.oficio_viagens(numero=12, ano=2026, protocolo=PROTOCOLO, servidores=self.equipe(quantos)),
            arquivo="Of.12-2026.pdf", assinantes=[("Chefe da Silva", "11144477735")], embrulhar=True,
        )

    def test_despacho_leva_a_folha_de_assinatura(self):
        importacao = self._importar([self._oficio_doc(), f.Doc(f.despacho(protocolo=PROTOCOLO), arquivo="DESPACHO_1.pdf", assinantes=[("Chefe da Silva", "11144477735")])])
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        despacho = self.anexos(Anexo.TIPO_DESPACHO)[0]
        textos = _textos(_bytes(despacho.arquivo))
        self.assertEqual(len(textos), 2)
        self.assertIn("DESPACHO", textos[0])
        self.assertIn("Documento: DESPACHO_1.pdf", textos[1])
        self.assertEqual(despacho.nome_original, "DESPACHO_1.pdf")

    def test_varios_despachos_entram_todos_na_ordem_do_processo(self):
        importacao = self._importar([
            self._oficio_doc(),
            f.Doc(f.despacho(protocolo=PROTOCOLO, destino="GAF"), arquivo="DESPACHO_1.pdf", assinantes=[("Chefe da Silva", "11144477735")]),
            f.Doc(f.despacho(protocolo=PROTOCOLO, destino="DG"), arquivo="DESPACHO_2.pdf", assinantes=[("Chefe da Silva", "11144477735")]),
        ])
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        despachos = self.anexos(Anexo.TIPO_DESPACHO)
        self.assertEqual([d.nome_original for d in despachos], ["DESPACHO_1.pdf", "DESPACHO_2.pdf"])
        self.assertIn("Ao GAF", _textos(_bytes(despachos[0].arquivo))[0])
        self.assertIn("Ao DG", _textos(_bytes(despachos[1].arquivo))[0])
        self.assertIn("2 despachos", importacao.resultado["resumo"])

    def test_despacho_substitui_os_anteriores_da_prestacao(self):
        Anexo.objects.create(prestacao=self.prestacao, tipo=Anexo.TIPO_DESPACHO, arquivo=SimpleUploadedFile("velho.pdf", pdf_minimo("VELHO")), nome_original="velho.pdf")
        self._importar([self._oficio_doc(), f.Doc(f.despacho(protocolo=PROTOCOLO), arquivo="DESPACHO_1.pdf")])
        self.assertEqual([d.nome_original for d in self.anexos(Anexo.TIPO_DESPACHO)], ["DESPACHO_1.pdf"])

    def test_rt_vai_para_o_servidor_pelo_cpf(self):
        # O nome impresso diferente do cadastro não importa: o CPF decide.
        nome, cpf = NOMES[1], self.cpfs[1]
        importacao = self._importar([
            self._oficio_doc(2),
            f.Doc(f.relatorio_tecnico(oficio="12/2026", nome="B. SOUZA", cpf=cpf), arquivo="RT.pdf", assinantes=[("Beltrana Souza", cpf)]),
        ])
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        self.assertEqual(len(self.anexos(Anexo.TIPO_RT_ASSINADO, self.ps[nome])), 1)
        self.assertEqual(len(self.anexos(Anexo.TIPO_RT_ASSINADO, self.ps[NOMES[0]])), 0)

    def test_diario_deitado_90_e_270_fica_paisagem_em_pe(self):
        for giro in (90, 270):
            with self.subTest(giro=giro):
                diario = f.girar_conteudo(f.diario_bordo(oficio="12/2026", protocolo=PROTOCOLO), giro)
                pdf = f.processo_eprotocolo(
                    [self._oficio_doc(), f.Doc(diario, arquivo=f"Diario_{giro}.pdf", embrulhar=True)],
                    protocolo=PROTOCOLO, numero_ano="12/2026",
                )
                self.enviar(pdf, nome=f"Processo_{giro}.pdf")
                anexo = self.anexos(Anexo.TIPO_DB_ASSINADO)[-1]
                pagina = ler_paginas(_bytes(anexo.arquivo))[0]
                self.assertTrue(pagina.em_paisagem)
                self.assertEqual(rotacao_para_ficar_em_pe(pagina), pagina.rotacao)  # em pé, não de cabeça para baixo
                self.assertIn(pagina.rotacao, (90, 270))
                # O cru fica guardado, como veio no processo.
                cru = ler_paginas(_bytes(anexo.arquivo_original))[0]
                self.assertEqual(cru.rotacao, 0)
                self.assertIn("(girado)", self.importacao().resultado["resumo"])

    def test_n_comprovantes_com_valor_e_data_por_cpf_mascarado_e_por_nome(self):
        fulano, beltrana, cicrano = NOMES
        docs = [
            self._oficio_doc(3),
            # CPF mascarado no meio (Pix do BB) e nas pontas (transferência do Bradesco).
            f.Doc(f.comprovante("bb_pix", nome=fulano, cpf=self.cpfs[0], valor="580,00", data="22/09/2026"), arquivo="pix_fulano.pdf"),
            f.Doc(f.comprovante("bradesco_transferencia", nome=beltrana, cpf=self.cpfs[1], valor="300,00", data="23/09/2026"), arquivo="ted_beltrana.pdf"),
            # Saque no terminal: só o nome do cliente.
            f.Doc(f.comprovante("bb_saque", nome=cicrano, cpf=self.cpfs[2], valor="250,00", data="24/09/2026"), arquivo="saque_cicrano.pdf"),
            # Um segundo comprovante do mesmo servidor, mais antigo: entram os dois.
            f.Doc(f.comprovante("caixa_saque", nome=fulano, cpf=self.cpfs[0], valor="100,00", data="20/09/2026"), arquivo="saque_fulano.pdf"),
        ]
        importacao = self._importar(docs)
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA, importacao.plano)

        def dados(nome):
            return [(a.valor, a.data_operacao, a.operacao) for a in self.anexos(Anexo.TIPO_COMPROVANTE, self.ps[nome])]

        self.assertEqual(dados(fulano), [(Decimal("580.00"), date(2026, 9, 22), "pix"), (Decimal("100.00"), date(2026, 9, 20), "saque")])
        self.assertEqual(dados(beltrana), [(Decimal("300.00"), date(2026, 9, 23), "transferencia")])
        self.assertEqual(dados(cicrano), [(Decimal("250.00"), date(2026, 9, 24), "saque")])
        self.assertIn("4 comprovantes", importacao.resultado["resumo"])

        # O chip da lista mostra valor e data; com dois, o total e o período.
        lista = self.client.get(reverse("viagens_prestacoes:index"))
        self.assertContains(lista, "R$ 300,00 · 23/09/2026")
        self.assertContains(lista, "2 comprovantes")
        self.assertContains(lista, "R$ 680,00 · 20/09 a 22/09/2026")

    def test_comprovante_so_imagem_sem_ocr_vai_para_a_conferencia(self):
        imagem = f.pagina_imagem(f.comprovante("bb_saque", nome=NOMES[0], cpf=self.cpfs[0]))
        importacao = self._importar([self._oficio_doc(), f.Doc(imagem, arquivo="comprovante.pdf", inserido_por="Fulano De Tal")])
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        self.assertFalse(self.prestacao.documentos_anexos.exists())
        plano = Plano.de_json(importacao.plano)
        item = plano.itens[-1]
        self.assertTrue(item.conferir)

        # Na conferência: comprovante de Fulano, com valor e data digitados.
        url = reverse("viagens_prestacoes:importacao_aplicar", args=[importacao.pk])
        self.client.post(url, {
            "prestacao": str(self.prestacao.pk), "acao": "aplicar",
            f"doc-{item.ordem}-destino": Anexo.TIPO_COMPROVANTE,
            f"doc-{item.ordem}-servidor": str(self.ps[NOMES[0]].pk),
            f"doc-{item.ordem}-valor": "R$ 580,00", f"doc-{item.ordem}-data": "2026-09-21",
            f"doc-{item.ordem}-operacao": "saque", f"doc-{item.ordem}-giro": "0",
        })
        importacao.refresh_from_db()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        comprovante = self.anexos(Anexo.TIPO_COMPROVANTE, self.ps[NOMES[0]])[0]
        self.assertEqual((comprovante.valor, comprovante.data_operacao, comprovante.operacao), (Decimal("580.00"), date(2026, 9, 21), "saque"))

    def test_girar_na_conferencia_grava_o_giro(self):
        imagem = f.pagina_imagem(f.diario_bordo(oficio="12/2026"), girar=90)
        importacao = self._importar([self._oficio_doc(), f.Doc(imagem, arquivo="Diario.pdf")])
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        item = next(i for i in Plano.de_json(importacao.plano).itens if i.destino == Anexo.TIPO_DB_ASSINADO)
        self.assertTrue(item.rotacao_incerta)
        palpite = item.rotacao_de(item.paginas[0])
        self.client.post(reverse("viagens_prestacoes:importacao_aplicar", args=[importacao.pk]), {
            "prestacao": str(self.prestacao.pk), f"doc-{item.ordem}-destino": Anexo.TIPO_DB_ASSINADO, f"doc-{item.ordem}-giro": "180",
        })
        anexo = self.anexos(Anexo.TIPO_DB_ASSINADO)[0]
        self.assertEqual(PdfReader(BytesIO(_bytes(anexo.arquivo))).pages[0].rotation, (palpite + 180) % 360)

    def test_convalidacao_sem_rt_avisa(self):
        # Convalidação: o ofício foi criado depois da saída da viagem.
        roteiro = self.fixture.roteiro
        roteiro.saida_dt = timezone.make_aware(datetime(2026, 9, 1, 8, 0))
        roteiro.save()
        Oficio.objects.filter(pk=self.oficio.pk).update(data_criacao=date(2026, 9, 10))
        importacao = self._importar([self._oficio_doc(2), f.Doc(f.despacho(protocolo=PROTOCOLO), arquivo="DESPACHO_1.pdf")])
        avisos = " ".join(importacao.resultado["avisos"])
        self.assertIn("Convalidação: falta o relatório técnico assinado de", avisos)
        self.assertIn(NOMES[0], avisos)
        self.assertIn("Convalidação: falta o diário de bordo assinado.", avisos)

    def test_autorizacao_nao_cobra_rt_nem_diario(self):
        importacao = self._importar([self._oficio_doc(), f.Doc(f.despacho(protocolo=PROTOCOLO), arquivo="DESPACHO_1.pdf")])
        self.assertFalse(any("Convalidação" in aviso for aviso in importacao.resultado["avisos"]))


class RepeticaoEFalhaTests(ImportacaoBase):
    def test_reimportar_o_mesmo_arquivo_avisa_e_mostra_a_anterior(self):
        pdf = f.processo_viagens(servidores=self.equipe(1))
        self.enviar(pdf)
        primeira = self.importacao()
        anexos = self.prestacao.documentos_anexos.count()

        resposta = self.enviar(pdf, nome="outro_nome.pdf")
        self.assertEqual(ImportacaoProcesso.objects.count(), 1)
        self.assertRedirects(resposta, reverse("viagens_prestacoes:importacao_detalhe", args=[primeira.pk]), fetch_redirect_response=False)
        self.assertTrue(any("já foi importado" in m for m in _mensagens(resposta)))
        self.assertEqual(self.prestacao.documentos_anexos.count(), anexos)

    def test_reimportar_depois_de_descartar_analisa_de_novo(self):
        pdf = self.processo(protocolo="27.000.000-1", numero_ano="99/2026")
        ImportacaoProcesso.objects.create(hash_sha256=__import__("hashlib").sha256(pdf).hexdigest(), situacao=ImportacaoProcesso.SITUACAO_DESCARTADA, arquivo=SimpleUploadedFile("x.pdf", pdf))
        self.enviar(pdf)
        self.assertEqual(ImportacaoProcesso.objects.count(), 2)

    def test_falha_no_meio_nao_deixa_anexo_nem_arquivo_orfao(self):
        antigo = Anexo.objects.create(prestacao=self.prestacao, tipo=Anexo.TIPO_DESPACHO, arquivo=SimpleUploadedFile("antigo.pdf", pdf_minimo("ANTIGO")), nome_original="antigo.pdf")
        pdf = f.processo_viagens(servidores=self.equipe(3))
        plano = analisar(pdf, "Processo.pdf")
        self.assertTrue(plano.pronto)
        importacao = registrar_importacao(pdf, "Processo.pdf", plano)

        from .importacao import aplicacao

        def arquivos():
            raiz = Path(settings.MEDIA_ROOT)
            return {str(p.relative_to(raiz)).replace("\\", "/") for p in raiz.rglob("*") if p.is_file()}

        antes = arquivos()
        real = aplicacao._criar_anexo
        chamadas = []

        def quebra_no_quinto(*args, **kwargs):
            chamadas.append(1)
            if len(chamadas) == 5:
                raise RuntimeError("disco cheio")
            return real(*args, **kwargs)

        with mock.patch.object(aplicacao, "_criar_anexo", side_effect=quebra_no_quinto):
            with self.assertRaises(RuntimeError):
                aplicar_importacao(importacao)

        self.assertEqual(list(self.prestacao.documentos_anexos.all()), [antigo])
        antigo.refresh_from_db()
        self.assertEqual(_bytes(antigo.arquivo)[:5], b"%PDF-")
        importacao.refresh_from_db()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        # Os quatro anexos criados antes da falha sumiram do disco com a transação.
        self.assertEqual(arquivos(), antes)
        self.assertIn(antigo.arquivo.name, antes)
        self.assertIn(importacao.arquivo.name, antes)

    def test_carimbo_error_nao_derruba_a_importacao(self):
        from .carimbo_services import CarimboError

        ps = self.ps[NOMES[0]]
        ps.numero_solicitacao = "2026001234"
        ps.save(update_fields=["numero_solicitacao"])

        def estoura(anexo, *, prestacao):
            # Grava alguma coisa antes de estourar: o savepoint tem de desfazer só isso.
            anexo.arquivo_original.save("cru.pdf", SimpleUploadedFile("cru.pdf", b"%PDF-1.4"), save=False)
            anexo.save(update_fields=["arquivo_original"])
            raise CarimboError("Não foi possível localizar a âncora do servidor.")

        with mock.patch("viagens_prestacoes.carimbo_services.preparar_e_carimbar", side_effect=estoura):
            self.enviar(f.processo_viagens(servidores=self.equipe(1)))

        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_APLICADA)
        oficio = self.anexos(Anexo.TIPO_OFICIO_ASSINADO)[0]
        self.assertFalse(oficio.arquivo_original)
        self.assertTrue(any("ajuste a posição do nº da solicitação" in aviso for aviso in importacao.resultado["avisos"]))
        self.assertEqual(len(self.anexos(Anexo.TIPO_COMPROVANTE, ps)), 1)

    def test_oficio_embrulhado_nao_e_carimbado_no_lugar_errado(self):
        """Lacuna L2: na página embrulhada as coordenadas saem erradas; vai para o ajuste manual."""
        ps = self.ps[NOMES[0]]
        ps.numero_solicitacao = "2026001234"
        ps.save(update_fields=["numero_solicitacao"])
        referencia = f.pagina([f"{NOMES[0]}        2026001234"])
        with mock.patch("viagens_prestacoes.services.gerar_oficio_prestacao_pdf", return_value=referencia):
            self.enviar(f.processo_viagens(servidores=self.equipe(1)))
        importacao = self.importacao()
        oficio = self.anexos(Anexo.TIPO_OFICIO_ASSINADO)[0]
        self.assertFalse(oficio.carimbos.exists())
        self.assertTrue(any("Ajuste a posição do nº da solicitação de " + NOMES[0] in aviso for aviso in importacao.resultado["avisos"]))


class EnvioTests(ImportacaoBase):
    def test_limite_proprio_aceita_processo_maior_que_o_limite_geral(self):
        pdf = f.processo_viagens(servidores=self.equipe(1))
        with override_settings(PRIVATE_UPLOAD_MAX_BYTES=1024, IMPORTACAO_MAX_BYTES=10 * 1024 * 1024):
            self.enviar(pdf)
        self.assertEqual(self.importacao().situacao, ImportacaoProcesso.SITUACAO_APLICADA)

    def test_passar_do_limite_do_importador_recusa(self):
        pdf = f.processo_viagens(servidores=self.equipe(1))
        with override_settings(IMPORTACAO_MAX_BYTES=1024):
            resposta = self.enviar(pdf)
        self.assertFalse(ImportacaoProcesso.objects.exists())
        self.assertTrue(any("limite" in m for m in _mensagens(resposta)))

    def test_arquivo_que_nao_e_pdf_e_recusado_pela_politica_central(self):
        resposta = self.enviar(b"%PDF-mentira", nome="processo.pdf")
        self.assertFalse(ImportacaoProcesso.objects.exists())
        self.assertTrue(any("PDF válido" in m for m in _mensagens(resposta)))

    def test_xhr_recebe_json(self):
        pdf = f.processo_viagens(servidores=self.equipe(1))
        resposta = self.client.post(
            reverse("viagens_prestacoes:importacao_enviar"),
            {"arquivo": SimpleUploadedFile("p.pdf", pdf, content_type="application/pdf")},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resposta.json()["url"], reverse("viagens_prestacoes:importacao_detalhe", args=[self.importacao().pk]))

    def test_sem_permissao_de_operador_recebe_403(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group

        leitor = get_user_model().objects.create_user(username="so_leitura")
        from .test_helpers import autorizar_viagens

        autorizar_viagens(leitor)
        leitor.groups.remove(Group.objects.get(name="VIAGENS_OPERADOR"))
        self.client.force_login(leitor)
        resposta = self.enviar(f.processo_viagens(servidores=self.equipe(1)))
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(ImportacaoProcesso.objects.exists())

    def test_telas_da_lista_mostram_o_importador(self):
        lista = self.client.get(reverse("viagens_prestacoes:index"))
        self.assertContains(lista, "Importar processo do eProtocolo")
        self.assertContains(lista, "data-importar-soltar")
        self.assertContains(lista, reverse("viagens_prestacoes:importacao_enviar_prestacao", args=[self.prestacao.pk]))
        self.assertContains(lista, "js/prestacoes-importar.js")

    def test_tela_de_conferencia_tem_miniaturas_e_giro(self):
        imagem = f.pagina_imagem(f.comprovante("bb_saque", nome=NOMES[0], cpf=self.cpfs[0]))
        pdf = f.processo_eprotocolo([f.Doc(imagem, arquivo="c.pdf")], protocolo=PROTOCOLO, numero_ano="12/2026")
        resposta = self.enviar(pdf, seguir=True)
        self.assertContains(resposta, "data-imp-canvas")
        self.assertContains(resposta, "data-imp-girar")
        self.assertContains(resposta, "vendor/pdfjs/pdf.min.js")
        self.assertContains(resposta, "Aplicar")
        arquivo = self.client.get(reverse("viagens_prestacoes:importacao_arquivo", args=[self.importacao().pk]))
        self.assertEqual(arquivo["Content-Type"], "application/pdf")

    def test_processo_guardado_nao_e_orfao_para_a_limpeza(self):
        from io import StringIO

        from django.core.management import call_command

        self.enviar(f.processo_viagens(servidores=self.equipe(1)))
        importacao = self.importacao()
        self.assertTrue(importacao.arquivo.name.startswith("viagens_prestacoes/importacoes/"))
        saida = StringIO()
        call_command("limpar_arquivos_orfaos", stdout=saida)
        self.assertNotIn(importacao.arquivo.name, saida.getvalue())
        for anexo in self.prestacao.documentos_anexos.all():
            self.assertNotIn(anexo.arquivo.name, saida.getvalue())

    def test_descartar(self):
        pdf = self.processo(protocolo="27.000.000-1", numero_ano="99/2026")
        self.definir_protocolo("", Oficio.PROTOCOLO_ORIGEM_MANUAL)
        self.criar_prestacao(numero=99, ano=2026, servidores=[self.criar_servidor("OUTRA PESSOA")])
        self.enviar(pdf)
        importacao = self.importacao()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_ANALISADA)
        self.client.post(reverse("viagens_prestacoes:importacao_descartar", args=[importacao.pk]))
        importacao.refresh_from_db()
        self.assertEqual(importacao.situacao, ImportacaoProcesso.SITUACAO_DESCARTADA)


class ComprovanteAvulsoTests(ImportacaoBase):
    """Só o comprovante (foto ou PDF do banco), sem ofício nem protocolo."""

    def _comprovante(self, **dados):
        dados.setdefault("nome", NOMES[0])
        dados.setdefault("cpf", self.cpfs[0])
        dados.setdefault("valor", "100,00")
        dados.setdefault("data", timezone.localdate().strftime("%d/%m/%Y"))
        return f.comprovante("bb_saque", **dados)

    def test_acha_a_prestacao_pelo_servidor_do_comprovante(self):
        plano = analisar(self._comprovante(), "comprovante.pdf")
        self.assertEqual(plano.prestacao_id, self.prestacao.pk)
        self.assertEqual(plano.camada, "comprovante")
        self.assertTrue(plano.identificacao_segura, plano.avisos)
        item = next(i for i in plano.itens if i.tipo_lido == "comprovante")
        self.assertEqual(item.servidor_prestacao_id, self.ps[NOMES[0]].pk)

    def test_mesmo_servidor_em_duas_prestacoes_abertas_vai_para_conferencia(self):
        self.criar_prestacao(numero=13, ano=2026, servidores=[self.servidores[0]])
        plano = analisar(self._comprovante(), "comprovante.pdf")
        self.assertFalse(plano.identificacao_segura)
        self.assertGreaterEqual(len(plano.candidatos), 2)

    def test_prestacao_finalizada_nao_recebe_comprovante_avulso(self):
        self.ps[NOMES[0]].definir_finalizada(True)
        plano = analisar(self._comprovante(), "comprovante.pdf")
        self.assertNotEqual(plano.prestacao_id, self.prestacao.pk)
