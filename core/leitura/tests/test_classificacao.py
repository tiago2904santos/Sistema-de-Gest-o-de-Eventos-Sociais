from django.test import SimpleTestCase

from core.leitura import classificacao as c
from core.leitura.pdf import ler_paginas
from core.leitura.tests import fabrica as f


def _texto(dados):
    return ler_paginas(dados)[0].corpo


class ClassificarTests(SimpleTestCase):
    """Cada modelo que o sistema imprime (e os do processo de pagamento) cai no tipo certo."""

    def test_todos_os_tipos(self):
        casos = {
            c.OFICIO: [f.oficio_viagens(), f.oficio_viagens(convalidacao=False), f.oficio_coffee_break()],
            c.DESPACHO: [f.despacho()],
            c.JUSTIFICATIVA: [f.justificativa()],
            c.TERMO_AUTORIZACAO: [f.termo_autorizacao()],
            c.RT: [f.relatorio_tecnico()],
            c.DIARIO_BORDO: [f.diario_bordo()],
            c.ORDEM_SERVICO: [f.ordem_servico()],
            c.PLANO_TRABALHO: [f.plano_trabalho()],
            c.NOTA_FISCAL: [f.nota_fiscal()],
            c.CERTIFICO: [f.certifico()],
            c.CERTIDAO: [f.certidao(tipo) for tipo in ("FEDERAL", "ESTADUAL", "MUNICIPAL", "TRABALHISTA", "FGTS")],
            c.CONTRATO: [f.contrato()],
            c.ADITIVO: [f.aditivo()],
            c.NOTA_EMPENHO: [f.nota_empenho()],
            c.NOTA_LIQUIDACAO: [f.nota_liquidacao()],
            c.EMAIL: [f.email_impresso()],
            c.COMPROVANTE: [f.comprovante(modelo) for modelo in f.MODELOS_COMPROVANTE],
        }
        for esperado, documentos in casos.items():
            for posicao, dados in enumerate(documentos):
                with self.subTest(tipo=esperado, caso=posicao):
                    tipo, confianca, evidencias = c.classificar(_texto(dados))
                    self.assertEqual(tipo, esperado)
                    self.assertGreaterEqual(confianca, 0.6)
                    self.assertTrue(evidencias)

    def test_capa_do_eprotocolo(self):
        tipo, _, _ = c.classificar(_texto(f.capa_eprotocolo()))
        self.assertEqual(tipo, c.CAPA)

    def test_referencia_ao_oficio_nao_faz_de_rt_ou_diario_um_oficio(self):
        self.assertEqual(c.classificar("Ref. ao Ofício 12/2026\nNome FULANO")[0], c.RT)
        self.assertEqual(c.classificar("Referente ao Ofício: 12/2026\nE-protocolo: 26.613.666-8")[0], c.DIARIO_BORDO)

    def test_despacho_que_cita_aditivo_e_oficio_no_assunto(self):
        texto = (
            "DEPARTAMENTO DE POLICIA CIVIL\nProtocolo: 26.613.666-8\n"
            "Assunto: CONTRATO 0762/2024 - TERMO ADITIVO No 0355/2025 - OFÍCIO 12/2026\n"
            "PADARIA LTDAInteressado:\nAo GAF,\nEncaminhamos.\nDESPACHO"
        )
        tipo, confianca, _ = c.classificar(texto)
        self.assertEqual(tipo, c.DESPACHO)
        self.assertGreater(confianca, 0.8)

    def test_certifico_que_cita_a_nota_e_liquidacao_que_cita_o_empenho(self):
        self.assertEqual(c.classificar(_texto(f.certifico()))[0], c.CERTIFICO)
        self.assertEqual(c.classificar(_texto(f.nota_liquidacao()))[0], c.NOTA_LIQUIDACAO)

    def test_nome_do_arquivo_e_pista_fraca(self):
        tipo, confianca, evidencias = c.classificar("", "15 - Comprovante_saque_fulano.pdf")
        self.assertEqual(tipo, c.COMPROVANTE)
        self.assertLess(confianca, 0.5)
        self.assertIn("nome do arquivo", evidencias[0])
        # O texto vence o nome.
        self.assertEqual(c.classificar(_texto(f.relatorio_tecnico()), "DESPACHO_1.pdf")[0], c.RT)
        # "CONTRATO…TERMOADITIVO" no nome é aditivo.
        self.assertEqual(c.classificar("", "CONTRATOLOTE1TERMOADITIVO.pdf")[0], c.ADITIVO)

    def test_sem_sinal(self):
        self.assertEqual(c.classificar("Lorem ipsum dolor sit amet."), (c.DESCONHECIDO, 0.0, []))
        self.assertEqual(c.classificar("")[0], c.DESCONHECIDO)

    def test_rotulos_para_todos_os_tipos(self):
        self.assertEqual(set(c.TIPOS), set(c.ROTULOS))
        self.assertIn(c.DESCONHECIDO, c.TIPOS)


class ComprovanteDeFotoTests(SimpleTestCase):
    """Texto de OCR de foto do comprovante do caixa eletrônico do BB."""

    def test_transferencia_do_cartao_para_conta_com_ocr_estragado(self):
        from core.leitura.classificacao import COMPROVANTE, classificar

        texto = (
            "23/09/2020 BANCO DO BRAS 17:29:05\nCOMPROVANTE Di TRANSFERENCIA\n"
            "DE CARTAO DE CREDITO PARA CONTA CORRENTE\nCLIENTE: FULANO DE TAL\n"
            "DATA DA TRANSFERENCIA 23/09/202t\nVALOR TOTAL 871,65\n"
            "TRANSFERIDO PARA:\nCLIENTE: FULANO DE TAL\nNR.AUTENTICACAO 0.CFF.B9C\n"
        )
        tipo, confianca, _ = classificar(texto)
        self.assertEqual(tipo, COMPROVANTE)
        self.assertGreaterEqual(confianca, 0.8)
