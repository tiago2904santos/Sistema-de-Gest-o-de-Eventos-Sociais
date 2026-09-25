"""Leitura do volume do eProtocolo (sintético) e de PDF avulso em documentos."""

import os
import re
import shutil
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock
from unittest import skipUnless

from django.test import SimpleTestCase
from django.test import override_settings

from core.leitura import classificacao as c
from core.leitura.eprotocolo import ler_processo
from core.leitura.ocr import LeituraOCR
from core.leitura.pdf import rotacao_para_ficar_em_pe
from core.leitura.tests import fabrica as f

PROTOCOLO = "26.613.666-8"


def _tipos(processo):
    return [d.tipo for d in processo.documentos]


@override_settings(OCR_ATIVO=False)
class ProcessoDeViagensTests(SimpleTestCase):
    """Ofício → despacho → RT → diário (deitado) → comprovantes, como no pedido do usuário."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cpf = f.gerar_cpf(31)
        cls.cpf2 = f.gerar_cpf(32)
        cls.chefe = f.gerar_cpf(33)
        cls.docs = [
            f.Doc(f.oficio_viagens(numero=12, ano=2026, protocolo=PROTOCOLO,
                                   servidores=[("FULANO DE TAL", cls.cpf), ("CICLANO SOUZA", cls.cpf2)]),
                  arquivo="Of.12-2026.pdf", assinantes=[("Chefe da Silva", cls.chefe)], embrulhar=True),
            f.Doc(f.despacho(protocolo=PROTOCOLO), arquivo="DESPACHO_1.pdf", assinantes=[("Delegado Geral", f.gerar_cpf(34))]),
            f.Doc(f.relatorio_tecnico(nome="FULANO DE TAL", cpf=cls.cpf), arquivo="RT_fulano.pdf",
                  assinantes=[("Fulano de Tal", cls.cpf)]),
            f.Doc(f.relatorio_tecnico(nome="CICLANO SOUZA", cpf=cls.cpf2), arquivo="RT_ciclano.pdf"),
            f.Doc(f.juntar(f.girar_conteudo(f.diario_bordo(), 90), f.girar_conteudo(f.diario_bordo(), 90)),
                  arquivo="Diario.pdf", embrulhar=True),
            f.Doc(f.comprovante("bb_saque", nome="FULANO DE TAL", cpf=cls.cpf, valor="580,00"), arquivo="saque.pdf"),
            f.Doc(f.comprovante("nubank_pix", nome="CICLANO SOUZA", cpf=cls.cpf2, valor="290,00"), arquivo="pix.pdf",
                  inserido_por="Ciclano Souza"),
        ]
        cls.dados = f.processo_eprotocolo(cls.docs, protocolo=PROTOCOLO, numero_ano="12/2026")
        cls.processo = ler_processo(cls.dados, "a1b2-Processo_26.613.666-8_1.pdf")

    def test_identificacao_do_volume(self):
        p = self.processo
        self.assertTrue(p.eh_eprotocolo)
        self.assertEqual(p.protocolo, "266136668")
        self.assertEqual(p.volume, 1)
        self.assertEqual(p.capa["numero_ano"], "12/2026")
        self.assertEqual(p.capa["protocolo"], "266136668")
        self.assertEqual(p.capa["assunto"], "DIARIAS")
        self.assertEqual(p.capa["detalhamento"], "PRESTACAO DE CONTAS DE DIARIAS")
        self.assertEqual(p.capa["em"].date(), date(2026, 9, 21))
        self.assertEqual(p.avisos, [])

    def test_documentos_na_ordem_com_tipos(self):
        self.assertEqual(
            _tipos(self.processo),
            [c.CAPA, c.OFICIO, c.DESPACHO, c.RT, c.RT, c.DIARIO_BORDO, c.COMPROVANTE, c.COMPROVANTE],
        )
        titulos = [d.titulo for d in self.processo.documentos]
        self.assertEqual(titulos[1:3], ["Of.12-2026.pdf", "DESPACHO_1.pdf"])
        self.assertEqual([d.ordem for d in self.processo.documentos], list(range(1, 9)))

    def test_folha_de_assinatura_vai_com_o_documento(self):
        oficio, despacho, rt, rt2 = self.processo.documentos[1:5]
        self.assertEqual(oficio.paginas, [1, 2])
        self.assertEqual(oficio.folhas_assinatura, [2])
        self.assertEqual(oficio.paginas_de_conteudo, [1])
        self.assertEqual(despacho.paginas, [3, 4])
        self.assertEqual(rt.folhas_assinatura, [6])
        self.assertEqual(rt2.folhas_assinatura, [])

    def test_assinaturas_com_cpf_parcial_e_quem_inseriu(self):
        oficio = self.processo.documentos[1]
        self.assertEqual(len(oficio.assinaturas), 1)
        assinatura = oficio.assinaturas[0]
        self.assertEqual((assinatura.tipo, assinatura.nome), ("Avançada", "Chefe da Silva"))
        self.assertEqual(assinatura.cpf_meio, self.chefe[3:9])
        self.assertEqual(assinatura.local, "DPC/ASCOM")
        self.assertEqual(assinatura.quando.strftime("%d/%m/%Y %H:%M"), "21/09/2026 13:18")
        self.assertEqual(oficio.inserido_por, "Maria Servidora da Silva")
        self.assertEqual(self.processo.documentos[-1].inserido_por, "Ciclano Souza")
        self.assertTrue(oficio.codigo)
        self.assertNotEqual(oficio.codigo, self.processo.documentos[2].codigo)

    def test_dados_extraidos(self):
        _capa, oficio, despacho, rt, rt2, diario, saque, pix = self.processo.documentos
        self.assertEqual((oficio.dados["numero"], oficio.dados["ano"]), (12, 2026))
        self.assertEqual(oficio.dados["cpfs"], [self.cpf, self.cpf2])
        self.assertTrue(oficio.dados["convalidacao"])
        self.assertEqual(despacho.dados["destino"], "GAF")
        self.assertEqual((rt.dados["cpf"], rt2.dados["cpf"]), (self.cpf, self.cpf2))
        self.assertEqual(diario.dados["protocolo"], "266136668")
        self.assertEqual((saque.dados["operacao"], saque.dados["valor"]), ("saque", Decimal("580.00")))
        self.assertEqual((pix.dados["operacao"], pix.dados["valor"], pix.dados["cpf_meio"]), ("pix", Decimal("290.00"), self.cpf2[3:9]))

    def test_so_o_diario_deitado_manda_girar(self):
        girar = {p.indice: rotacao_para_ficar_em_pe(p) for p in self.processo.paginas if rotacao_para_ficar_em_pe(p)}
        diario = self.processo.documentos[5]
        self.assertEqual(girar, {i: 270 for i in diario.paginas})

    def test_author_do_pdf_nao_e_guardado(self):
        self.assertNotIn("00000000191", repr([asdict(d) for d in self.processo.documentos]) + repr(self.processo.capa))


@override_settings(OCR_ATIVO=False)
class ProcessosProntosDaFabricaTests(SimpleTestCase):
    """Os processos prontos da fábrica (que os testes dos importadores usam) leem como os reais."""

    def test_processo_de_viagens(self):
        servidores = [("FULANO DE TAL", f.gerar_cpf(71)), ("CICLANO SOUZA", f.gerar_cpf(72))]
        processo = ler_processo(f.processo_viagens(servidores=servidores, modelos_comprovante=("bb_saque", "nubank_pix")))
        self.assertEqual(
            _tipos(processo),
            [c.CAPA, c.OFICIO, c.DESPACHO, c.RT, c.RT, c.DIARIO_BORDO, c.COMPROVANTE, c.COMPROVANTE],
        )
        self.assertEqual([d.dados.get("cpf") for d in processo.documentos[3:5]], [cpf for _, cpf in servidores])
        self.assertEqual(processo.avisos, [])

    def test_processo_do_coffee_break_como_o_real(self):
        processo = ler_processo(f.processo_coffee_break())
        self.assertEqual(_tipos(processo), AmostrasReaisTests.ESPERADO[16])
        self.assertEqual(processo.capa["numero_ano"], "123/2026")


@override_settings(OCR_ATIVO=False)
class SegmentacaoTests(SimpleTestCase):
    def _docs(self):
        return [
            f.Doc(f.oficio_coffee_break(), arquivo="Of.123.pdf", assinantes=[("Chefe", f.gerar_cpf(41))]),
            f.Doc(f.nota_fiscal(), arquivo="NF8952.pdf", assinantes=[("Fiscal", f.gerar_cpf(42))]),
            f.Doc(f.certifico(), arquivo="CERTIFICO8952.pdf", assinantes=[("Fiscal", f.gerar_cpf(42))]),
            f.Doc(f.certidao("FGTS"), arquivo="FGTS.pdf"),
            f.Doc(f.aditivo(paginas_=3), arquivo="CONTRATOLOTE1TERMOADITIVO.pdf", aninhado=True, embrulhar=True),
            f.Doc(f.contrato(paginas_=4), arquivo="CONTRATOLOTE1.pdf", aninhado=True),
            f.Doc(f.despacho(), arquivo="DESPACHO_1.pdf"),
            f.Doc(f.nota_empenho(), arquivo="2026NE108096.pdf"),
            f.Doc(f.nota_liquidacao(), arquivo="LIQ.pdf"),
        ]

    _ESPERADO = [c.CAPA, c.OFICIO, c.NOTA_FISCAL, c.CERTIFICO, c.CERTIDAO, c.ADITIVO, c.CONTRATO, c.DESPACHO,
                 c.NOTA_EMPENHO, c.NOTA_LIQUIDACAO]

    def test_pelos_marcadores(self):
        processo = ler_processo(f.processo_eprotocolo(self._docs()))
        self.assertEqual(_tipos(processo), self._ESPERADO)
        aditivo, contrato = processo.documentos[5:7]
        self.assertTrue(aditivo.aninhado and contrato.aninhado)
        self.assertEqual(len(aditivo.paginas), 3)
        self.assertEqual(len(contrato.paginas), 4)
        self.assertFalse(processo.documentos[1].aninhado)

    def test_sem_marcadores_pelo_codigo_de_validacao(self):
        processo = ler_processo(f.processo_eprotocolo(self._docs(), marcadores=False))
        self.assertEqual(_tipos(processo), self._ESPERADO)
        self.assertEqual(processo.documentos[1].titulo, "Of.123.pdf")  # da folha de assinatura

    def test_sem_marcadores_nem_codigo_pelo_mov(self):
        processo = ler_processo(f.processo_eprotocolo(self._docs(), marcadores=False, codigos=False))
        self.assertEqual(_tipos(processo), self._ESPERADO)
        self.assertEqual([len(d.paginas) for d in processo.documentos], [1, 2, 2, 2, 1, 3, 4, 1, 1, 1])

    def test_sem_metadados_reconhece_pelo_rodape(self):
        processo = ler_processo(f.processo_eprotocolo(self._docs(), criador=False))
        self.assertTrue(processo.eh_eprotocolo)
        self.assertEqual(processo.protocolo, "266136668")
        self.assertIsNone(processo.volume)

    def test_volume_2_sem_capa_e_folhas_faltando(self):
        dados = f.processo_eprotocolo(self._docs()[:3], volume=2, fls_inicial=40, mov_inicial=20)
        processo = ler_processo(dados)
        self.assertEqual(processo.volume, 2)
        self.assertEqual(processo.capa, {})
        self.assertEqual(_tipos(processo), [c.OFICIO, c.NOTA_FISCAL, c.CERTIFICO])
        self.assertEqual(processo.avisos, [])

        pulando = f.juntar(
            f.emoldurar(f.relatorio_tecnico(), fls="1", mov="1"),
            f.emoldurar(f.relatorio_tecnico(), fls="4", mov="2"),
        )
        self.assertIn("Faltam folhas", " ".join(ler_processo(pulando).avisos))


@override_settings(OCR_ATIVO=False)
class AvulsoTests(SimpleTestCase):
    def test_pdf_avulso_separado_por_tipo(self):
        cpf, cpf2 = f.gerar_cpf(51), f.gerar_cpf(52)
        dados = f.juntar(
            f.relatorio_tecnico(nome="FULANO DE TAL", cpf=cpf),
            f.pagina(["Informações complementares do relatório (continuação)."]),
            f.relatorio_tecnico(nome="CICLANO SOUZA", cpf=cpf2),
            f.diario_bordo(),
            f.diario_bordo(),
            f.comprovante("caixa_saque", cpf=cpf),
            f.comprovante("itau_pix", cpf=cpf2),
            f.pagina_imagem(f.comprovante()),
        )
        processo = ler_processo(dados, "prestacao.pdf")
        self.assertFalse(processo.eh_eprotocolo)
        self.assertEqual(
            [(d.tipo, d.paginas) for d in processo.documentos],
            [(c.RT, [0, 1]), (c.RT, [2]), (c.DIARIO_BORDO, [3, 4]), (c.COMPROVANTE, [5]), (c.COMPROVANTE, [6]),
             (c.DESCONHECIDO, [7])],
        )
        self.assertIn("sem leitura do texto", " ".join(processo.avisos))

    def test_nome_do_arquivo_nao_puxa_as_paginas_de_continuacao(self):
        dados = f.juntar(f.relatorio_tecnico(), f.pagina(["Informações complementares (continuação)."]), f.comprovante())
        processo = ler_processo(dados, "comprovantes.pdf")
        self.assertEqual([(d.tipo, d.paginas) for d in processo.documentos], [(c.RT, [0, 1]), (c.COMPROVANTE, [2])])

    def test_paginacao_junta_e_separa(self):
        dados = f.juntar(
            f.pagina(["COMPROVANTE DE PAGAMENTO", "Página 1 de 2"]),
            f.pagina(["COMPROVANTE DE PAGAMENTO", "Página 2 de 2"]),
            f.pagina(["COMPROVANTE DE PAGAMENTO", "Página 1 de 1"]),
        )
        self.assertEqual([d.paginas for d in ler_processo(dados).documentos], [[0, 1], [2]])

    def test_notas_fiscais_diferentes_em_sequencia(self):
        dados = f.juntar(f.nota_fiscal(numero=8952), f.nota_fiscal(numero=8954))
        processo = ler_processo(dados)
        self.assertEqual([d.dados["numero"] for d in processo.documentos], ["8952", "8954"])

    def test_imagem_png_vira_documento_de_uma_pagina(self):
        png = f.imagem_png(f.comprovante())
        processo = ler_processo(png, "foto.png")
        self.assertEqual(len(processo.paginas), 1)
        self.assertEqual(len(processo.documentos), 1)
        self.assertEqual(processo.documentos[0].titulo, "foto.png")

    def test_assinatura_digital_fora_do_eprotocolo(self):
        dados = f.pagina(["TERMO DE AUTORIZAÇÃO PARA PARTICIPAÇÃO EM EVENTOS DA ASCOM", "Eu FULANO DE TAL, CPF: 123.456.789-09,",
                          "Documento assinado digitalmente", "FULANO DE TAL", "Data: 21/09/2026 10:32:15-0300",
                          "Verifique em https://validar.iti.gov.br"])
        documento = ler_processo(dados).documentos[0]
        self.assertEqual([(a.tipo, a.nome) for a in documento.assinaturas], [("gov.br", "FULANO DE TAL")])


class OcrNoProcessoTests(SimpleTestCase):
    """Página sem texto: o texto do OCR classifica e extrai, até o limite."""

    def _leitura(self, _dados, indice):
        return LeituraOCR(0, f"COMPROVANTE DE SAQUE\nCLIENTE: FULANO DE TAL\nDATA 21/09/2026\nVALOR DO SAQUE R$ {100 + indice},00")

    @override_settings(OCR_MAX_PAGINAS=2)
    def test_ocr_ate_o_limite(self):
        dados = f.processo_eprotocolo([f.Doc(f.pagina_imagem(f.comprovante()), arquivo=f"c{i}.pdf") for i in range(3)])
        with mock.patch("core.leitura.ocr.disponivel", return_value=True), mock.patch(
            "core.leitura.ocr.analisar_pagina", side_effect=self._leitura
        ) as analisar:
            processo = ler_processo(dados)
        self.assertEqual(analisar.call_count, 2)
        lidos = processo.documentos[1:3]
        self.assertEqual([d.tipo for d in lidos], [c.COMPROVANTE, c.COMPROVANTE])
        self.assertEqual([d.dados["valor"] for d in lidos], [Decimal("101.00"), Decimal("102.00")])
        self.assertIn("texto lido por OCR", lidos[0].evidencias)
        self.assertTrue(processo.paginas[1].ocr)
        self.assertEqual(processo.paginas[1].angulo_texto, 0)
        self.assertFalse(processo.paginas[3].ocr)
        self.assertIn("o OCR leu 2", " ".join(processo.avisos))

    def test_na_pagina_so_de_imagem_o_ocr_decide_o_sentido(self):
        """O nº de página em pé não decide o sentido do diário escaneado deitado."""
        escaneado = f.pagina_imagem(f.diario_bordo(), girar=90)
        from pypdf import PdfReader
        from reportlab.pdfgen import canvas
        import io

        carimbo = io.BytesIO()
        tela = canvas.Canvas(carimbo, pagesize=PdfReader(io.BytesIO(escaneado)).pages[0].mediabox[2:])
        tela.setFont("Helvetica", 8)
        tela.drawString(20, 20, "Página 1 de 1")
        tela.save()
        pagina = PdfReader(io.BytesIO(escaneado)).pages[0]
        pagina.merge_page(PdfReader(io.BytesIO(carimbo.getvalue())).pages[0])
        from pypdf import PdfWriter

        escritor = PdfWriter()
        escritor.add_page(pagina)
        saida = io.BytesIO()
        escritor.write(saida)
        with mock.patch("core.leitura.ocr.disponivel", return_value=True), mock.patch(
            "core.leitura.ocr.analisar_pagina", return_value=LeituraOCR(270, "Ficha individual do veículo")
        ):
            processo = ler_processo(saida.getvalue())
        self.assertEqual(rotacao_para_ficar_em_pe(processo.paginas[0]), 270)
        self.assertEqual(processo.documentos[0].tipo, c.DIARIO_BORDO)

    @skipUnless(shutil.which("tesseract"), "tesseract não instalado")
    @override_settings(OCR_ATIVO=True, TESSERACT_CMD="", OCR_DPI=150)
    def test_comprovante_fotografado_de_verdade(self):
        cpf = f.gerar_cpf(61)
        foto = f.imagem_png(f.comprovante("caixa_saque", nome="JOANA DA SILVA PEREIRA", cpf=cpf, valor="432,10"), girar=90)
        processo = ler_processo(foto, "saque.png")
        documento = processo.documentos[0]
        self.assertEqual(documento.tipo, c.COMPROVANTE)
        self.assertEqual(documento.dados["valor"], Decimal("432.10"))
        self.assertEqual(documento.dados["operacao"], "saque")
        self.assertEqual(rotacao_para_ficar_em_pe(processo.paginas[0]), 270)


_AMOSTRAS = os.environ.get("LEITURA_AMOSTRAS_REAIS", "")


@skipUnless(_AMOSTRAS and Path(_AMOSTRAS).is_dir(), "defina LEITURA_AMOSTRAS_REAIS com a pasta dos processos reais")
@override_settings(OCR_ATIVO=False)
class AmostrasReaisTests(SimpleTestCase):
    """Validação local com os processos reais (fora do repositório: têm nomes e CPFs).

    `LEITURA_AMOSTRAS_REAIS=/pasta python manage.py test core.leitura` — lê
    todo `*Processo_*.pdf` da pasta e confere a estrutura do Coffee Break.
    """

    ESPERADO = {
        16: [c.CAPA, c.OFICIO, c.NOTA_FISCAL, c.CERTIFICO, c.NOTA_FISCAL, c.CERTIFICO] + [c.CERTIDAO] * 5
        + [c.ADITIVO, c.CONTRATO, c.DESPACHO, c.NOTA_EMPENHO, c.NOTA_LIQUIDACAO],
        12: [c.CAPA, c.OFICIO, c.NOTA_FISCAL, c.CERTIFICO] + [c.CERTIDAO] * 5 + [c.ADITIVO, c.CONTRATO, c.DESPACHO],
    }

    def test_processos_reais(self):
        arquivos = sorted(Path(_AMOSTRAS).glob("*Processo_*.pdf"))
        self.assertTrue(arquivos)
        for arquivo in arquivos:
            with self.subTest(arquivo=arquivo.name):
                processo = ler_processo(arquivo.read_bytes(), arquivo.name)
                self.assertTrue(processo.eh_eprotocolo)
                self.assertEqual(_tipos(processo), self.ESPERADO[len(processo.documentos)])
                self.assertTrue(re.fullmatch(r"\d{9}", processo.protocolo))
                self.assertEqual(
                    [p.indice for p in processo.paginas if rotacao_para_ficar_em_pe(p) not in (None, p.rotacao)], []
                )
