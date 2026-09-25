from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from core.leitura import texto
from core.leitura.tests import fabrica as f


class NormalizarTests(SimpleTestCase):
    def test_tira_acento_ligadura_e_espacos(self):
        self.assertEqual(texto.normalizar("  Certiﬁcado  Nº 12 – Ofício ç "), "CERTIFICADO NO 12 - OFICIO C")

    def test_vazio(self):
        self.assertEqual(texto.normalizar(None), "")


class CpfTests(SimpleTestCase):
    def setUp(self):
        self.cpf = f.gerar_cpf(3)

    def test_formatado_e_cru_valido(self):
        corrido = f"CPF: {f.formatar_cpf(self.cpf)} e, sem máscara, {f.gerar_cpf(4)}."
        self.assertEqual(texto.achar_cpfs(corrido), [self.cpf, f.gerar_cpf(4)])

    def test_onze_digitos_soltos_so_com_digito_verificador(self):
        # Telefone com DDD tem 11 dígitos e não é CPF.
        self.assertEqual(texto.achar_cpfs("Fone 41999887766"), [])

    def test_formatado_com_digito_errado_ainda_vale(self):
        self.assertEqual(texto.achar_cpfs("CPF 123.456.789-00"), ["12345678900"])

    def test_nao_pega_pedaco_de_chave_de_nfe(self):
        self.assertEqual(texto.achar_cpfs("4126 0935 0147 1900 0166 5500 1000 0089 5212 2512 9059"), [])

    def test_mascarados_nos_dois_formatos(self):
        corrido = (
            f"(XXX.{self.cpf[3:6]}.{self.cpf[6:9]}-XX) ***.456.789-** 123.***.***-00 "
            "•••.111.222-•• \x7f\x7f\x7f.333.444-\x7f\x7f"
        )
        self.assertEqual(
            texto.achar_cpfs_mascarados(corrido),
            [("meio", self.cpf[3:9]), ("meio", "456789"), ("pontas", "12300"), ("meio", "111222"), ("meio", "333444")],
        )

    def test_mascara_do_ocr_so_no_modo_tolerante(self):
        self.assertEqual(texto.achar_cpfs_mascarados("CPF 000,512.222-.0"), [])
        self.assertEqual(texto.achar_cpfs_mascarados("CPF 000,512.222-.0", tolerante=True), [("meio", "512222")])
        self.assertEqual(texto.achar_cpfs_mascarados('CPF: 123.**."*-02', tolerante=True), [("pontas", "12302")])
        # CPF inteiro não vira máscara nem no modo tolerante.
        self.assertEqual(texto.achar_cpfs_mascarados("CPF 000.512.222-00", tolerante=True), [])


class ValorDataProtocoloTests(SimpleTestCase):
    def test_valores_no_formato_brasileiro(self):
        corrido = "Total R$ 1.600,00; parcela 800,00; preço 20,0000; PCPR 2026.050731.000; qtd 80"
        self.assertEqual(texto.achar_valores(corrido), [Decimal("1600.00"), Decimal("800.00")])

    def test_datas_em_varios_formatos(self):
        corrido = (
            "Curitiba, 21 de Setembro de 2026; emissão 18/09/26; assinado 2025.10.21; "
            "Nubank 03 SET 2026; 5/mar/2026; 31/02/2026; 1º de março de 2026"
        )
        self.assertEqual(
            texto.achar_datas(corrido),
            [date(2026, 9, 21), date(2026, 9, 18), date(2025, 10, 21), date(2026, 9, 3), date(2026, 3, 5), date(2026, 3, 1)],
        )

    def test_protocolo_descarta_rg(self):
        corrido = "RG: 12.345.678-9, RG n.º 98.765.432-1, Protocolo 26.613.666-8 e 26613666-8; PCPR 2026.050731.000"
        self.assertEqual(texto.achar_protocolos(corrido), ["266136668"])

    def test_cnpj(self):
        self.assertEqual(texto.achar_cnpjs("CNPJ 35.014.719/0001-66"), ["35014719000166"])
