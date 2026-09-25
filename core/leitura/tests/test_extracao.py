from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from core.leitura import classificacao as c
from core.leitura.extracao import dados_do_documento
from core.leitura.pdf import ler_paginas
from core.leitura.tests import fabrica as f


def _dados(tipo, dados_pdf):
    return dados_do_documento(tipo, ler_paginas(dados_pdf)[0].corpo)


class ViagensTests(SimpleTestCase):
    def setUp(self):
        self.cpf = f.gerar_cpf(11)
        self.cpf2 = f.gerar_cpf(12)

    def test_oficio_de_convalidacao(self):
        dados = _dados(c.OFICIO, f.oficio_viagens(numero=7, ano=2026, protocolo="26.613.666-8",
                                                  servidores=[("FULANO DE TAL", self.cpf), ("CICLANO", self.cpf2)]))
        self.assertEqual((dados["numero"], dados["ano"]), (7, 2026))
        self.assertEqual(dados["protocolo"], "266136668")
        self.assertEqual(dados["cpfs"], [self.cpf, self.cpf2])
        self.assertIs(dados["convalidacao"], True)
        self.assertEqual(dados["data"], date(2026, 9, 21))

    def test_oficio_de_autorizacao(self):
        self.assertIs(_dados(c.OFICIO, f.oficio_viagens(convalidacao=False))["convalidacao"], False)

    def test_oficio_do_coffee_break(self):
        dados = _dados(c.OFICIO, f.oficio_coffee_break())
        self.assertEqual((dados["numero"], dados["ano"]), (123, 2026))
        self.assertEqual(dados["pcpr_protocolo"], "2026.050731.000")
        self.assertEqual(dados["notas_fiscais"], ["8952", "8954"])
        self.assertEqual(dados["contrato"], "0762/2024")
        self.assertNotIn("convalidacao", dados)
        self.assertNotIn("protocolo", dados)

    def test_rt(self):
        dados = _dados(c.RT, f.relatorio_tecnico(oficio="07/2026", nome="FULANO DE TAL", cpf=self.cpf, diaria="R$ 1.160,00"))
        self.assertEqual(dados, {"oficio_numero": 7, "oficio_ano": 2026, "nome": "FULANO DE TAL", "cpf": self.cpf,
                                 "diaria": Decimal("1160.00")})

    def test_diario(self):
        dados = _dados(c.DIARIO_BORDO, f.diario_bordo(oficio="7/2026", protocolo="26.613.666-8", placa="ABC-1D23",
                                                      cpf_motorista=self.cpf))
        self.assertEqual((dados["oficio_numero"], dados["oficio_ano"]), (7, 2026))
        self.assertEqual(dados["protocolo"], "266136668")
        self.assertEqual(dados["placa"], "ABC1D23")
        self.assertEqual(dados["cpf_motorista"], self.cpf)

    def test_termo(self):
        dados = _dados(c.TERMO_AUTORIZACAO, f.termo_autorizacao(nome="JOANA DA SILVA", cpf=self.cpf, rg="12.345.678-9"))
        self.assertEqual(dados["nome"], "JOANA DA SILVA")
        self.assertEqual(dados["cpf"], self.cpf)
        self.assertEqual(dados["rg"], "123456789")
        self.assertEqual(dados["lotacao"], "ASCOM")

    def test_despacho(self):
        dados = _dados(c.DESPACHO, f.despacho(protocolo="26.613.666-8", destino="GAF", data="21/09/2026 10:03"))
        self.assertEqual(dados["protocolo"], "266136668")
        self.assertEqual(dados["data"], date(2026, 9, 21))
        self.assertEqual((dados["data_hora"].hour, dados["data_hora"].minute), (10, 3))
        self.assertIsNotNone(dados["data_hora"].tzinfo)
        self.assertEqual(dados["destino"], "GAF")
        self.assertEqual(dados["interessado"], "POLÍCIA CIVIL DO PARANÁ")
        self.assertEqual(dados["assunto"], "PRESTAÇÃO DE CONTAS DE DIÁRIAS - OFÍCIO 12/2026")

    def test_despacho_com_o_valor_colado_no_rotulo(self):
        """Como sai do eProtocolo real: "PADARIA … LTDAInteressado:" e "21/09/2026 10:03Data:"."""
        texto = (
            "Protocolo: 26.613.666-8\nAssunto: CONTRATO 0762/2024 - GMS 7339/2024 - TERMO ADITIVO\nNo 0355/2025\n"
            "PADARIA E CONFEITARIA LTDAInteressado:\n21/09/2026 10:03Data:\nAo GAF,\nEncaminhamos.\nDESPACHO"
        )
        dados = dados_do_documento(c.DESPACHO, texto)
        self.assertEqual(dados["assunto"], "CONTRATO 0762/2024 - GMS 7339/2024 - TERMO ADITIVO No 0355/2025")
        self.assertEqual(dados["interessado"], "PADARIA E CONFEITARIA LTDA")
        self.assertEqual(dados["destino"], "GAF")
        self.assertEqual(dados["data"], date(2026, 9, 21))

    def test_os_plano_e_justificativa(self):
        self.assertEqual(_dados(c.ORDEM_SERVICO, f.ordem_servico(numero=5, ano=2026)), {"numero": 5, "ano": 2026})
        self.assertEqual(_dados(c.PLANO_TRABALHO, f.plano_trabalho(numero=3, ano=2026)), {"numero": 3, "ano": 2026})
        self.assertEqual(_dados(c.JUSTIFICATIVA, f.justificativa())["data"], date(2026, 9, 21))


class ComprovanteTests(SimpleTestCase):
    def test_modelos_de_banco(self):
        cpf = f.gerar_cpf(21)
        for modelo, (operacao, banco, formato) in f.MODELOS_COMPROVANTE.items():
            with self.subTest(modelo=modelo):
                dados = _dados(c.COMPROVANTE, f.comprovante(modelo, nome="JOANA DA SILVA PEREIRA", cpf=cpf,
                                                            valor="1.234,56", data="21/09/2026", hora="10:32"))
                self.assertEqual(dados["valor"], Decimal("1234.56"))
                self.assertEqual(dados["data"], date(2026, 9, 21))
                self.assertTrue(dados["hora"].startswith("10:32"))
                self.assertEqual(dados["operacao"], operacao)
                self.assertEqual(dados["banco"], banco)
                self.assertEqual(dados["nome"].upper(), "JOANA DA SILVA PEREIRA")
                if formato == "meio":
                    self.assertEqual(dados["cpf_meio"], cpf[3:9])
                elif formato == "pontas":
                    self.assertEqual(dados["cpf_pontas"], cpf[:3] + cpf[9:])
                else:
                    self.assertNotIn("cpf_meio", dados)

    def test_pagador_e_favorecido_separados_no_pix(self):
        dados = _dados(c.COMPROVANTE, f.comprovante("bb_pix", nome="JOANA DA SILVA", pagador="Beltrano Pagador Souza"))
        self.assertEqual(dados["favorecido"], "Joana Da Silva")
        self.assertEqual(dados["pagador"], "Beltrano Pagador Souza")
        self.assertEqual(dados["nome"], "Joana Da Silva")

    def test_saldo_nao_e_o_valor(self):
        texto = "COMPROVANTE DE SAQUE\nSALDO DISPONIVEL R$ 9.999,99\nVALOR DO SAQUE R$ 300,00\nDATA 21/09/2026"
        self.assertEqual(dados_do_documento(c.COMPROVANTE, texto)["valor"], Decimal("300.00"))

    def test_texto_do_ocr_com_mascara_estragada(self):
        texto = "Comprovante de transferência\n21 SET 2026 - 10:32:15\nValor\nR$ 580,00\nPix\nDestino\nNome Joana Da Silva\nCPF 000,512.222-.0"
        dados = dados_do_documento(c.COMPROVANTE, texto)
        self.assertEqual(dados["cpf_meio"], "512222")
        self.assertEqual(dados["data"], date(2026, 9, 21))
        self.assertEqual(dados["nome"], "Joana Da Silva")

    def test_nada_achado_nao_vira_chave(self):
        self.assertEqual(dados_do_documento(c.COMPROVANTE, "texto qualquer"), {})
        self.assertEqual(dados_do_documento(c.DESCONHECIDO, "Protocolo 26.613.666-8"), {"protocolos": ["266136668"]})


class PagamentoTests(SimpleTestCase):
    def test_nota_fiscal(self):
        dados = _dados(c.NOTA_FISCAL, f.nota_fiscal(numero=8952, valor="1.600,00", emissao="18/09/2026"))
        self.assertEqual(dados["numero"], "8952")
        self.assertEqual(dados["serie"], "001")
        self.assertEqual(dados["emissao"], date(2026, 9, 18))
        self.assertEqual(dados["valor"], Decimal("1600.00"))
        self.assertEqual(dados["cnpj"], "35014719000166")
        self.assertEqual(len(dados["chave"]), 44)

    def test_certifico_e_certidoes(self):
        self.assertEqual(_dados(c.CERTIFICO, f.certifico(nota="8957")),
                         {"nota_fiscal": "8957", "cnpj": "35014719000166", "contrato": "0762/2024"})
        dados = _dados(c.CERTIDAO, f.certidao("FGTS", validade="04/10/2026"))
        self.assertEqual(dados["tipos"], ["FGTS"])
        self.assertEqual(dados["validade"], date(2026, 10, 4))

    def test_contrato_e_aditivo(self):
        self.assertEqual(_dados(c.CONTRATO, f.contrato())["numero"], "0762/2024")
        dados = _dados(c.ADITIVO, f.aditivo())
        self.assertEqual((dados["numero"], dados["contrato"], dados["protocolo"]), ("0355/2025", "0762/2024", "247407464"))

    def test_empenho_e_liquidacao(self):
        self.assertEqual(_dados(c.NOTA_EMPENHO, f.nota_empenho()),
                         {"numero": "2026NE108096", "emissao": date(2026, 9, 14), "valor": Decimal("17558.33"),
                          "cnpj": "35014719000166"})
        dados = _dados(c.NOTA_LIQUIDACAO, f.nota_liquidacao())
        self.assertEqual(dados["numero"], "2026NL105243")
        self.assertEqual(dados["empenho"], "2026NE108096")
        self.assertEqual(dados["valor"], Decimal("2400.00"))
        self.assertEqual([n["numero"] for n in dados["notas_fiscais"]], ["8952", "8954"])

    def test_capa_pelo_texto(self):
        texto = "Protocolo:\n26.613.666-8\nEm: 21/09/2026 10:00\n123/2026Nº/Ano"
        dados = dados_do_documento(c.CAPA, texto)
        self.assertEqual(dados["protocolo"], "266136668")
        self.assertEqual(dados["numero_ano"], "123/2026")
