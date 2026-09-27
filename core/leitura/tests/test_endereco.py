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
        self.assertEndereco("Endereço: Av. Brasil nº 45, bairro Jardim América, Cascavel/PR", "Av. Brasil nº 45", bairro="Jardim América")

    def test_avenida_por_extenso_sem_virgula(self):
        self.assertEndereco("Avenida das Torres 800 - Vila Nova", "Avenida das Torres 800", bairro="Vila Nova")

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
    # O logradouro e o número saem como escritos no e-mail: sem vírgula
    # inserida, com o "nº" e o "sem número" de quem escreveu.

    def test_como_escrito_sem_virgula(self):
        self.assertEndereco("rua antonio santos 45 centro", "rua antonio santos 45", bairro="centro")
        self.assertEndereco("ENDERECO RUA SAO PAULO 300 CENTRO", "RUA SAO PAULO 300", bairro="CENTRO")

    def test_n_ponto(self):
        self.assertEndereco("Rua Fictícia n. 45", "Rua Fictícia n. 45")

    def test_numero_por_extenso(self):
        self.assertEndereco("Rua Fictícia, número 45", "Rua Fictícia, número 45")

    def test_sem_numero_por_extenso(self):
        self.assertEndereco("Rua do Campo, sem número, Centro", "Rua do Campo, sem número", bairro="Centro")

    def test_numero_com_letra(self):
        self.assertEndereco("Rua Fictícia, 45A", "Rua Fictícia, 45A")

    def test_rua_sete_de_setembro(self):
        self.assertEndereco("Rua 7 de Setembro, 300", "Rua 7 de Setembro, 300")

    def test_rua_numerada(self):
        self.assertEndereco("Rua 15, 300 - Centro", "Rua 15, 300", bairro="Centro")

    def test_numero_nao_come_o_resto_da_frase(self):
        self.assertEndereco(
            "O evento será na Rua Fictícia 45 a partir das 9h, com 50 pessoas.", "Rua Fictícia 45"
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
            "Estamos em Campo Largo e o evento será na Rua Fictícia 45 a partir das 9h", "Rua Fictícia 45"
        )

    def test_linha_comum_nao_e_endereco(self):
        self.assertIsNone(endereco_no_texto("Estamos na linha de frente do atendimento."))

    def test_praca_em_maiusculas_depois_de_na(self):
        self.assertEndereco("EVENTO NA PRAÇA DA MATRIZ, S/N", "PRAÇA DA MATRIZ, S/N")

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

    def test_assinatura_nao_comeca_no_nome_citado_na_frase(self):
        texto = "Sou o Fulano Fictício, líder da juventude.\nEndereço: Rua Um, 10 - Centro\n\nFulano Fictício\n(45) 99999-0000"
        self.assertEndereco(texto, "Rua Um, 10", bairro="Centro", assinatura="Fulano Fictício\n(45) 99999-0000")

    # --- quebra de linha do e-mail no meio do endereço ---------------------------

    def test_quebra_depois_da_virgula(self):
        self.assertEndereco(
            "Local de entrega: Auditório da Delegacia Fictícia de Paranaguá, Rua Faria Um,\n350 - Centro, Paranaguá.\n"
            "Responsável pelo recebimento: Fulana.",
            "Rua Faria Um, 350", bairro="Centro",
        )

    def test_quebra_no_meio_do_nome(self):
        self.assertEndereco(
            "Entrega: Escola Fictícia de Polícia Civil do Paraná, Rua Professor Fulano Munhoz\n"
            "Mader, 2800 – Cidade Industrial, Curitiba – CEP 81350-010.\nQuem recebe: Fulano.",
            "Rua Professor Fulano Munhoz Mader, 2800", bairro="Cidade Industrial", cep="81350-010",
        )

    def test_quebra_dentro_do_parentese(self):
        self.assertEndereco(
            "Coffee para 18 pessoas, que será na Delegacia Fictícia de Rolândia (Rua Dom\n"
            "Pedro II, 300 - Centro). Pode entregar para mim.",
            "Rua Dom Pedro II, 300", bairro="Centro",
        )

    def test_quebra_depois_do_traco(self):
        self.assertEndereco(
            "Local: Centro de Convivência do Idoso de Sarandi, Rua das Flores, 90 - Jardim\nEsperança, Sarandi.\n"
            "Quem recebe: Fulana.",
            "Rua das Flores, 90", bairro="Jardim Esperança",
        )

    def test_linha_curta_nao_e_quebrada(self):
        self.assertEndereco("Rua das Palmeiras, 300\nFulano de Tal", "Rua das Palmeiras, 300")

    def test_texto_sem_quebra_pela_largura(self):
        # Linhas mais compridas que 80 colunas: a pessoa quebrou a linha, não o programa.
        texto = (
            "vai ser na escola municipal fictícia de são josé dos pinhais, rua joinville 2300, bairro borda do campo\n"
            "comeca as 8h ate umas 14h"
        )
        self.assertEndereco(texto, "rua joinville 2300", bairro="borda do campo")

    # --- bairro ------------------------------------------------------------------

    def test_bairro_composto(self):
        self.assertEndereco("Av. Tiradentes, 1120 - Zona 03, Maringá.", "Av. Tiradentes, 1120", bairro="Zona 03")
        self.assertEndereco("Rua Londrina, 250 - Bairro Alto, Curitiba.", "Rua Londrina, 250", bairro="Bairro Alto")

    def test_centro_de_cidade(self):
        self.assertEndereco("A feira será na Praça Rui Barbosa, centro de Curitiba.", "Praça Rui Barbosa", bairro="centro")
        self.assertEndereco(
            "Na Praça General Fictício, no Centro Histórico da Lapa, das 10h às 18h.",
            "Praça General Fictício", bairro="Centro Histórico",
        )

    def test_centro_minusculo_nao_leva_a_frase(self):
        self.assertEndereco(
            "o evento é na sede do sindicato rua sao paulo 612 centro precisa fazer rg de umas 100 pessoas",
            "rua sao paulo 612", bairro="centro",
        )

    def test_bairro_minusculo_depois_do_numero(self):
        self.assertEndereco("endereço av rui barbosa 1500 afonso pena\nsou a pedagoga", "av rui barbosa 1500", bairro="afonso pena")

    def test_bairro_fechando_o_parentese(self):
        self.assertEndereco(
            "Vai ser no Salão da Capela Fictícia (Rua Irmã Fulana, 55, Costeira).", "Rua Irmã Fulana, 55", bairro="Costeira"
        )
        self.assertEndereco("no auditório (Via do Conhecimento, km 1, Fraron).", "Via do Conhecimento, km 1", bairro="Fraron")

    def test_cidade_fechando_o_parentese_nao_e_bairro(self):
        self.assertEndereco("O encontro é em Araucária (Rua Um, 55, Araucária).", "Rua Um, 55")

    def test_bairro_citado_no_texto(self):
        self.assertEndereco(
            "amanhã tem a ação social aqui no bairro Guaíra\né na associação de moradores, rua brigadeiro franco 3800",
            "rua brigadeiro franco 3800", bairro="Guaíra",
        )
        self.assertEndereco(
            "A ação do Jardim Fictício será no Ginásio do Bairro, Rua Um, 150.", "Rua Um, 150", bairro="Jardim Fictício"
        )

    def test_bairro_no_nome_do_lugar(self):
        self.assertEndereco(
            "A próxima edição será no Tatuquara, na Rua da Cidadania do Tatuquara, Rua Olívio Fictício, 1350.",
            "Rua Olívio Fictício, 1350", bairro="Tatuquara",
        )

    # --- rodovia, outro logradouro depois do lugar ---------------------------------

    def test_rodovia_com_sigla_entre_parenteses(self):
        self.assertEndereco(
            "Local: Rodovia do Café (BR-277), km 115 - Itaqui.", "Rodovia do Café (BR-277), km 115", bairro="Itaqui"
        )

    def test_praca_seguida_do_logradouro(self):
        self.assertEndereco(
            "na Praça do Mirante - Av. Paranaguá, s/n - Caiobá, com emissão de RG", "Av. Paranaguá, s/n", bairro="Caiobá"
        )
        self.assertEndereco(
            "Local: Praça do Rio Bonito, Rua Pedro Fictício, 5000 - Campo de Santana",
            "Rua Pedro Fictício, 5000", bairro="Campo de Santana",
        )
        self.assertEndereco(
            "na Praça dos Namorados, Av. Atlântica, Centro de Guaratuba, no período de", "Av. Atlântica", bairro="Centro"
        )

    # --- CEP sem rótulo ---------------------------------------------------------------

    def test_cep_sem_rotulo_na_linha_da_cidade(self):
        self.assertEndereco(
            "Auditório do Centro de Estudos\nRua Sergipe, 900 - Centro\nLondrina - PR, 86010-360\nQuem recebe: Fulana",
            "Rua Sergipe, 900", bairro="Centro", cep="86010-360",
        )

    def test_cep_com_ponto_sem_rotulo(self):
        self.assertEndereco("Rua Um, 10 - Centro, 80.060-000", "Rua Um, 10", bairro="Centro", cep="80060-000")

    # --- carimbo e rodapé no fim do corpo ----------------------------------------------

    def test_carimbo_no_fim_do_corpo(self):
        texto = (
            "O seminário será no Hotel Fictício de Maringá. Recebe no local: Fulano.\n"
            "Divisão de Inteligência – PCPR\n"
            "Rua José Fictício, 376 – Centro – Curitiba/PR – CEP 80010-000"
        )
        self.assertIsNone(endereco_no_texto(texto))

    def test_carimbo_antes_do_documento_encaminhado(self):
        texto = (
            "Encaminho o protocolo para análise.\nProtocolo Geral - Gabinete Fictício\n"
            "Av. Iguaçu, 470 - Rebouças - Curitiba/PR\n------------------------------\nOfício nº 1/2026"
        )
        self.assertIsNone(endereco_no_texto(texto))

    def test_rodape_com_telefone(self):
        texto = "Ainda não temos data.\nSetor Gente & Gestão\n(43) 3251-4040\nRua Pará, 777 - Centro - Cambé/PR"
        self.assertIsNone(endereco_no_texto(texto))

    def test_endereco_do_evento_na_ultima_linha_continua(self):
        self.assertEndereco("Local do evento:\nGinásio Fictício\nRua Um, 10 - Centro", "Rua Um, 10", bairro="Centro")
        self.assertEndereco(
            "É para os alunos da Escola Fictícia, aqui em Cascavel\nRua Paraná, 3200, Centro. Uns 90 alunos",
            "Rua Paraná, 3200", bairro="Centro",
        )
