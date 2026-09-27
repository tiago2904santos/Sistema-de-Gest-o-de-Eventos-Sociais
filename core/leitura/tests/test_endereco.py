"""Endereços em e-mails inventados: nenhum endereço aqui é de pessoa real."""

from django.test import SimpleTestCase

from core.leitura.endereco import Endereco, endereco_no_texto, formatar_cep


class FormatarCepTests(SimpleTestCase):
    def test_formatos(self):
        self.assertEqual(formatar_cep("84010000"), "84010-000")
        self.assertEqual(formatar_cep("84.010-000"), "84010-000")
        self.assertEqual(formatar_cep("84010-000"), "84010-000")
        self.assertEqual(formatar_cep("8401000"), "")
        self.assertEqual(formatar_cep(""), "")


class EnderecoNoTextoTests(SimpleTestCase):
    def ler(self, texto, **kwargs) -> Endereco:
        endereco = endereco_no_texto(texto, **kwargs)
        self.assertIsNotNone(endereco, texto)
        return endereco

    def assertEndereco(self, texto, logradouro, complemento="", bairro="", cep="", **kwargs):
        e = self.ler(texto, **kwargs)
        self.assertEqual(
            (e.logradouro_numero, e.complemento, e.bairro, e.cep),
            (logradouro, complemento, bairro, cep),
            texto,
        )
        return e

    # --- tipos de logradouro -------------------------------------------------

    def test_rua_com_numero_bairro_e_cep(self):
        e = self.assertEndereco(
            "O evento será realizado na Rua XV de Novembro, 1200 - Centro - CEP 84010-000.",
            "Rua XV de Novembro, 1200", bairro="Centro", cep="84010-000",
        )
        self.assertTrue(e.ancorado)
        self.assertEqual(e.confianca, "A")
        self.assertIn("Rua XV de Novembro", e.trecho)

    def test_r_abreviado(self):
        self.assertEndereco("Fica na R. Coronel Fictício, 55.", "R. Coronel Fictício, 55")

    def test_avenida_abreviada_com_no(self):
        self.assertEndereco("Endereço: Av. Brasil nº 45, bairro Jardim América, Cascavel/PR", "Av. Brasil, 45", bairro="Jardim América")

    def test_avenida_por_extenso_sem_virgula(self):
        self.assertEndereco("Avenida das Torres 800 - Vila Nova", "Avenida das Torres, 800", bairro="Vila Nova")

    def test_av_sem_ponto(self):
        self.assertEndereco("Av Central, 10", "Av Central, 10")

    def test_alameda_abreviada(self):
        self.assertEndereco(
            "Al. Dom Pedro II, 1000, Jd. das Flores, Ponta Grossa - PR, 84010000",
            "Al. Dom Pedro II, 1000", bairro="Jd. das Flores", cep="84010-000",
        )

    def test_alameda_por_extenso(self):
        self.assertEndereco("Alameda dos Ipês, 77", "Alameda dos Ipês, 77")

    def test_travessa(self):
        self.assertEndereco("Travessa Imaginária, 3 - Centro", "Travessa Imaginária, 3", bairro="Centro")

    def test_tv_abreviada(self):
        self.assertEndereco("Tv. Oliveira, 12 - Vila Estrela", "Tv. Oliveira, 12", bairro="Vila Estrela")

    def test_praca_sem_numero(self):
        self.assertEndereco(
            "Precisamos de 30 kits na Praça Barão do Rio Branco, s/n - Centro.",
            "Praça Barão do Rio Branco, s/n", bairro="Centro",
        )

    def test_pca_abreviada(self):
        self.assertEndereco("Pça. Central Fictícia, 20", "Pça. Central Fictícia, 20")

    def test_rodovia_com_km(self):
        e = self.assertEndereco("Entrega na Rodovia PR-445, km 12, zona rural", "Rodovia PR-445, km 12")
        self.assertTrue(e.ancorado)

    def test_rod_abreviada(self):
        self.assertEndereco("Rod. BR-277, km 3,5", "Rod. BR-277, km 3,5")

    def test_rodovia_so_pela_sigla(self):
        self.assertEndereco("O encontro será na PR-445, km 12.", "PR-445, km 12")

    def test_br_sem_km_nao_e_endereco(self):
        self.assertIsNone(endereco_no_texto("A equipe vai pela BR-277 até Guarapuava."))

    def test_estrada(self):
        self.assertEndereco("Estrada da Graciosa, km 5", "Estrada da Graciosa, km 5")

    def test_largo(self):
        self.assertEndereco("Largo da Ordem, 10 - São Francisco", "Largo da Ordem, 10", bairro="São Francisco")

    def test_servidao(self):
        self.assertEndereco("Servidão Paz, 20", "Servidão Paz, 20")

    def test_linha_rural(self):
        self.assertEndereco("Linha São Roque, s/n, interior de Toledo", "Linha São Roque, s/n")

    # --- número ------------------------------------------------------------

    def test_n_ponto(self):
        self.assertEndereco("Rua Fictícia n. 45", "Rua Fictícia, 45")

    def test_numero_por_extenso(self):
        self.assertEndereco("Rua Fictícia, número 45", "Rua Fictícia, 45")

    def test_sem_numero_por_extenso(self):
        self.assertEndereco("Rua do Campo, sem número, Centro", "Rua do Campo, s/n", bairro="Centro")

    def test_numero_com_letra(self):
        self.assertEndereco("Rua Fictícia, 45A", "Rua Fictícia, 45A")

    def test_rua_sete_de_setembro(self):
        self.assertEndereco("Rua 7 de Setembro, 300", "Rua 7 de Setembro, 300")

    def test_rua_numerada(self):
        self.assertEndereco("Rua 15, 300 - Centro", "Rua 15, 300", bairro="Centro")

    def test_numero_nao_come_o_resto_da_frase(self):
        self.assertEndereco(
            "O evento será na Rua Fictícia 45 a partir das 9h, com 50 pessoas.", "Rua Fictícia, 45"
        )

    def test_hora_nao_e_numero(self):
        e = self.ler("Rua Fictícia, 14h, auditório")
        self.assertEqual(e.logradouro_numero, "Rua Fictícia")

    # --- complemento e bairro ------------------------------------------------

    def test_complemento_sala_e_bloco(self):
        self.assertEndereco(
            "RUA SETE DE SETEMBRO, 55, SALA 2, BLOCO B - B. UVARANAS - CEP 84.030-000",
            "RUA SETE DE SETEMBRO, 55", complemento="SALA 2, BLOCO B", bairro="UVARANAS", cep="84030-000",
        )

    def test_complemento_andar(self):
        self.assertEndereco("Av. Fictícia, 900, 3º andar - Centro", "Av. Fictícia, 900", complemento="3º andar", bairro="Centro")

    def test_bairro_com_rotulo(self):
        self.assertEndereco("Rua das Acácias, 10, bairro Jardim América", "Rua das Acácias, 10", bairro="Jardim América")

    def test_bairro_b_ponto(self):
        self.assertEndereco("Rua das Acácias, 10 - B. Uvaranas", "Rua das Acácias, 10", bairro="Uvaranas")

    def test_bairro_vila(self):
        self.assertEndereco("Rua das Acácias, 10, Vila Nova", "Rua das Acácias, 10", bairro="Vila Nova")

    def test_bairro_jd(self):
        self.assertEndereco("Rua das Acácias, 10, Jd. das Flores", "Rua das Acácias, 10", bairro="Jd. das Flores")

    def test_bairro_solto_antes_da_cidade(self):
        self.assertEndereco("Rua das Acácias, 10, Uvaranas, Ponta Grossa/PR", "Rua das Acácias, 10", bairro="Uvaranas")

    def test_cidade_com_uf_nao_e_bairro(self):
        self.assertEndereco("Rua das Acácias, 10, Ponta Grossa - PR", "Rua das Acácias, 10")

    # --- CEP -----------------------------------------------------------------

    def test_cep_com_ponto(self):
        self.assertEndereco("Rua Um, 10 - CEP: 84.010-000", "Rua Um, 10", cep="84010-000")

    def test_cep_so_digitos(self):
        self.assertEndereco("Rua Um, 10, CEP 84010000", "Rua Um, 10", cep="84010-000")

    def test_so_o_cep(self):
        e = self.assertEndereco("Favor entregar no CEP 84010-000.", "", cep="84010-000")
        self.assertEqual(e.confianca, "A")

    def test_cep_da_assinatura_nao_conta(self):
        self.assertIsNone(endereco_no_texto("Bom dia, segue o pedido.", assinatura="Fulano\nCEP 80000-000"))

    # --- em linhas próprias ----------------------------------------------------

    def test_endereco_em_linhas_proprias(self):
        e = self.assertEndereco(
            "Local: Ginásio de Esportes Municipal\nRua das Palmeiras, 300 - Jardim Carvalho\nCEP 84015-000\n\nAtt",
            "Rua das Palmeiras, 300", bairro="Jardim Carvalho", cep="84015-000",
        )
        self.assertTrue(e.ancorado)

    def test_bairro_na_linha_de_baixo(self):
        self.assertEndereco("Rua das Palmeiras, 300\nBairro Centro\n\nObrigado", "Rua das Palmeiras, 300", bairro="Centro")

    def test_linha_seguinte_que_nao_continua(self):
        self.assertEndereco("Rua das Palmeiras, 300\nO evento começa às 9h.", "Rua das Palmeiras, 300")

    # --- maiúsculas, minúsculas, acentos -----------------------------------------

    def test_sem_acento_e_maiusculas(self):
        self.assertEndereco("AVENIDA JOAO FICTICIO, 1500 - CENTRO", "AVENIDA JOAO FICTICIO, 1500", bairro="CENTRO")

    def test_tudo_minusculo(self):
        self.assertEndereco("rua das flores, 123, vila nova", "rua das flores, 123", bairro="vila nova")

    def test_minusculo_sem_numero_nao_e_endereco(self):
        self.assertIsNone(endereco_no_texto("a rua estava fechada ontem"))

    def test_praca_comum_nao_e_endereco(self):
        self.assertIsNone(endereco_no_texto("A reunião acontece na praça central às 14h."))

    def test_campo_largo_nao_e_logradouro(self):
        self.assertEndereco(
            "Estamos em Campo Largo e o evento será na Rua Fictícia 45 a partir das 9h", "Rua Fictícia, 45"
        )

    def test_linha_comum_nao_e_endereco(self):
        self.assertIsNone(endereco_no_texto("Estamos na linha de frente do atendimento."))

    def test_praca_em_maiusculas_depois_de_na(self):
        self.assertEndereco("EVENTO NA PRAÇA DA MATRIZ, S/N", "PRAÇA DA MATRIZ, s/n")

    def test_texto_sem_endereco(self):
        self.assertIsNone(endereco_no_texto("Bom dia, gostaríamos de agendar uma palestra no dia 10/10."))
        self.assertIsNone(endereco_no_texto(""))

    # --- preferência: evento x assinatura ------------------------------------------

    def test_ignora_endereco_so_da_assinatura(self):
        self.assertIsNone(endereco_no_texto("Bom dia, pedimos uma palestra.", assinatura="Fulano de Tal\nRua da Sede, 10 - Centro"))

    def test_ignora_assinatura_colada_no_texto(self):
        texto = "Pedimos uma palestra.\n\nFulano de Tal\nRua da Sede, 10 - Centro"
        self.assertIsNone(endereco_no_texto(texto, assinatura="Fulano de Tal\nRua da Sede, 10 - Centro"))

    def test_ignora_o_que_vem_depois_do_fecho(self):
        self.assertIsNone(endereco_no_texto("Bom dia, segue pedido.\n\nAtenciosamente,\nFulano\nRua da Sede, 10 - Centro"))

    def test_prefere_o_do_evento_ao_da_assinatura(self):
        texto = "O evento será na Rua do Evento, 500 - Centro.\n\nAtenciosamente,\nFulano\nRua da Sede, 10"
        self.assertEndereco(texto, "Rua do Evento, 500", bairro="Centro")

    def test_mesmo_endereco_no_corpo_e_na_assinatura_vale(self):
        texto = "O evento será na nossa sede, Rua da Sede, 10."
        self.assertEndereco(texto, "Rua da Sede, 10", assinatura="Fulano\nRua da Sede, 10")

    def test_prefere_o_ancorado(self):
        texto = (
            "Nossa secretaria fica na Rua da Secretaria, 20 - Centro.\n\n"
            "O evento será realizado no endereço Av. do Evento, 900."
        )
        e = self.assertEndereco(texto, "Av. do Evento, 900")
        self.assertTrue(e.ancorado)

    def test_ancora_entrega(self):
        texto = "Moro na Rua Um, 1.\nA entrega deve ser feita na Rua Dois, 2."
        self.assertEndereco(texto, "Rua Dois, 2")

    def test_residente_perde(self):
        texto = "Fulano, residente na Rua Um, 1, pede palestra no Colégio X, Rua Dois, 2."
        self.assertEndereco(texto, "Rua Dois, 2")

    def test_sem_ancora_fica_o_primeiro(self):
        texto = "Rua Primeira, 10.\nRua Segunda, 20."
        e = self.assertEndereco(texto, "Rua Primeira, 10")
        self.assertEqual(e.confianca, "M")

    def test_endereco_campo_do_formulario(self):
        e = self.ler("Rua Um, 10, sala 3 - Centro")
        self.assertEqual(e.endereco, "Rua Um, 10, sala 3")

    def test_cep_formatado_logo_depois_do_nome(self):
        self.assertEndereco("Rua Um, 84010-000", "Rua Um", cep="84010-000")
