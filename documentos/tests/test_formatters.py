from decimal import Decimal

from django.test import SimpleTestCase

from documentos.services.formatters import (
    format_city_uf,
    format_currency_br,
    format_document_display,
    format_institucional_rodape_linha,
    format_valor_extenso_display,
    preserve_known_acronyms,
)


class FormatDocumentDisplayTests(SimpleTestCase):
    def test_gabinete_particulas(self):
        s = format_document_display("GABINETE DO DELEGADO GERAL ADJUNTO")
        self.assertEqual(s, "Gabinete do Delegado Geral Adjunto")

    def test_demo_prefix(self):
        s = format_document_display("[DEMO] SERVIDOR 05")
        self.assertEqual(s, "[Demo] Servidor 05")

    def test_preserve_rg_cpf_in_sentence(self):
        s = format_document_display("DOCUMENTO RG 123 CPF 456")
        self.assertIn("RG", s)
        self.assertIn("CPF", s)


class FormatCityUfTests(SimpleTestCase):
    def test_londrina_pr(self):
        self.assertEqual(format_city_uf("LONDRINA/PR"), "Londrina/PR")

    def test_spaces_around_slash(self):
        self.assertEqual(format_city_uf("CURITIBA  /  pr"), "Curitiba/PR")


class PreserveAcronymsTests(SimpleTestCase):
    def test_token_with_punctuation(self):
        self.assertEqual(preserve_known_acronyms("(pr)"), "(PR)")


class FormatValorExtensoTests(SimpleTestCase):
    def test_maiusculas_para_frase(self):
        self.assertEqual(
            format_valor_extenso_display("CENTO E CINQUENTA REAIS"),
            "Cento e cinquenta reais",
        )

    def test_normaliza_espacos(self):
        self.assertEqual(
            format_valor_extenso_display("CEM   REAIS"),
            "Cem reais",
        )


class FormatCurrencyBrTests(SimpleTestCase):
    def test_milhar_e_centavos(self):
        self.assertEqual(format_currency_br(Decimal("1500")), "R$1.500,00")

    def test_decimal_half(self):
        self.assertEqual(format_currency_br(Decimal("1500.5")), "R$1.500,50")

    def test_vazio(self):
        self.assertEqual(format_currency_br(None), "")
        self.assertEqual(format_currency_br(""), "")


class FormatInstitucionalRodapeTests(SimpleTestCase):
    def test_rodape_title_case_e_email_minusculo(self):
        inst = {
            "divisao": "ASSESSORIA DE COMUNICACAO SOCIAL",
            "logradouro": "RUA IZABEL GOMES POSSELT",
            "numero": "103",
            "bairro": "ALTO BOQUEIRAO",
            "cidade_endereco": "CURITIBA",
            "uf": "PR",
            "cep_formatado": "81850-716",
            "telefone_formatado": "(41) 3235-6476",
            "email": "COMUNICACAO@PC.PR.GOV.BR",
        }
        out = format_institucional_rodape_linha(inst)
        self.assertIn("Assessoria de Comunicacao Social", out)
        self.assertIn("Social - Rua", out)
        self.assertIn("Rua Izabel Gomes Posselt", out)
        self.assertIn("Curitiba", out)
        self.assertIn("PR", out)
        self.assertIn("81850-716", out)
        self.assertIn("(41) 3235-6476", out)
        self.assertIn("comunicacao@pc.pr.gov.br", out)
