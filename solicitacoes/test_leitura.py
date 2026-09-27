"""Leituras próprias do evento social (`solicitacoes.leitura`): local, quem pede, CIN, serviços."""

from django.test import SimpleTestCase

from core.leitura.mensagem import Mensagem

from .leitura import desquebrar, local_do_evento, quantidade_de_cin, solicitante_do_pedido, texto_do_pedido


class DesquebrarTests(SimpleTestCase):
    def test_junta_linha_quebrada_e_mantem_lista(self):
        texto = (
            "Solicitamos a equipe para a ação de cidadania que acontece no Parque de\n"
            "Exposições Municipal, no sábado.\n"
            "Local: Ginásio\n"
            "Serviços: RG"
        )
        self.assertIn("Parque de Exposições Municipal", desquebrar(texto))
        self.assertIn("\nServiços: RG", desquebrar(texto))

    def test_linha_que_acaba_em_preposicao_junta_mesmo_com_rotulo_embaixo(self):
        texto = "Pedimos o mutirão de emissão da carteira de identidade no dia 3, na sede do\nSindicato: Rua X, 10."
        self.assertIn("na sede do Sindicato: Rua X", desquebrar(texto))


class LocalTests(SimpleTestCase):
    def local(self, corpo, **kw):
        achado = local_do_evento(corpo, **kw)
        return achado.valor if achado else None

    def test_nome_do_lugar_sem_endereco(self):
        self.assertEqual(self.local("Será no Ginásio Municipal Tancredo Neves, Rua das Flores, 100."), "Ginásio Municipal Tancredo Neves")
        self.assertEqual(self.local("Será no Salão Paroquial São Pedro (Rua A, 5 - Centro)."), "Salão Paroquial São Pedro")

    def test_rotulo_local(self):
        self.assertEqual(self.local("Data: 10/10\nLocal: Casa da Cultura - Av. Brasil, 50\nHorário: 9h"), "Casa da Cultura")

    def test_nome_proprio_vence_descricao_generica(self):
        corpo = "Na primeira edição fizemos na igreja do bairro. Agora será no Centro Comunitário Vila Nova."
        self.assertEqual(self.local(corpo), "Centro Comunitário Vila Nova")

    def test_correcao_do_local(self):
        corpo = "Será no Parque Central? Não: o local mudou para a Praça da Matriz, por causa da obra."
        self.assertEqual(self.local(corpo), "Praça da Matriz")

    def test_lugar_sem_nome_nao_vale(self):
        self.assertIsNone(self.local("A data será definida em conjunto com essa instituição."))
        self.assertIsNone(self.local("Provavelmente em março de 2027, no centro."))

    def test_proprio_lugar_citado_antes(self):
        corpo = "Sou a Joana do CRAS Vila Rica. O atendimento é no próprio CRAS, rua A, 10."
        self.assertEqual(self.local(corpo), "CRAS Vila Rica")

    def test_minusculas(self):
        self.assertEqual(self.local("vai ser na escola municipal santos dumont, rua b 20"), "escola municipal santos dumont")
        self.assertEqual(self.local("A feira é no pátio da igreja, Av. Sete, 10."), "pátio da igreja")

    def test_abreviacao_no_nome(self):
        self.assertEqual(self.local("A FEIRA SERA NA PRACA CEL. JOAO SILVA, CENTRO."), "PRACA CEL. JOAO SILVA")


class SolicitanteTests(SimpleTestCase):
    def pedido(self, corpo="", assinatura="", remetente=""):
        return solicitante_do_pedido(Mensagem(corpo=corpo, assinatura=assinatura, remetente_nome=remetente))

    def test_tratamento_sai_do_nome(self):
        for tratamento in ("Prof.", "Dr.", "Dra.", "Frei", "Ir.", "Cap. PM RR", "Enf.", "Profª", "Companheiro"):
            with self.subTest(tratamento):
                achado = self.pedido(assinatura=f"{tratamento} Carlos Alberto Lima\nCoordenador\n(41) 3333-4444")
                self.assertEqual(achado.nome, "Carlos Alberto Lima")
                self.assertIn("Coordenador", achado.cargo)

    def test_tratamento_que_e_cargo_vira_cargo_na_falta_de_outro(self):
        achado = self.pedido(assinatura="Diretora Paula Ramos\n(41) 3333-4444")
        self.assertEqual((achado.nome, achado.cargo), ("Paula Ramos", "Diretora"))

    def test_autoridade_e_nao_quem_mandou_em_nome_dela(self):
        assinatura = "JOSÉ CARLOS PRADO\nPrefeito Municipal\n\nEnviado em nome do Prefeito por:\nAna Lima - Assessora\n(42) 3333-1111"
        achado = self.pedido(assinatura=assinatura)
        self.assertEqual(achado.nome, "José Carlos Prado")
        self.assertEqual(achado.cargo, "Prefeito Municipal")

    def test_assinatura_no_fim_do_corpo_com_o_telefone_dela(self):
        corpo = (
            "A festa é dia 5.\n\nMeu número pra inscrição é 42 99999-1111\n\n"
            "Pastor Marcos Paulo Dias, Igreja Batista Central, 42 98888-2222"
        )
        achado = self.pedido(corpo=corpo)
        self.assertEqual(achado.nome, "Marcos Paulo Dias")
        self.assertIn("Igreja Batista Central", achado.cargo)
        self.assertEqual(achado.telefone.valor, "(42) 98888-2222")

    def test_rotulo_responsavel_em_caixa_alta(self):
        corpo = "PEDIMOS RG NO DIA 3.\n\nRESPONSAVEL: JOAO PEDRO ALVES\nSECRETARIO MUNICIPAL DE SAUDE\nFONE (44) 3531-0000"
        achado = self.pedido(corpo=corpo)
        self.assertEqual(achado.nome, "Joao Pedro Alves")
        self.assertEqual(achado.cargo, "SECRETARIO MUNICIPAL DE SAUDE")

    def test_nome_em_minusculas_com_cargo_embaixo(self):
        achado = self.pedido(corpo="queremos rg dia 7\n\njoao da silva\npresidente da associacao\n41 99187-0000")
        self.assertEqual((achado.nome, achado.cargo), ("Joao da Silva", "presidente da associacao"))

    def test_grupo_de_whatsapp_e_apresentacao(self):
        corpo = "Maria Céu: aqui é a Maria do CRAS Centro\nMaria Céu: RG, umas 90 pessoas\nMaria Céu: Maria Souza Lima 45 3266-0000"
        achado = self.pedido(corpo=corpo)
        self.assertEqual(achado.nome, "Maria Souza Lima")
        self.assertEqual(achado.cargo, "CRAS Centro")

    def test_sou_voluntaria(self):
        achado = self.pedido(corpo="Oi! Sou voluntária do Natal Solidário, em Araucária.", assinatura="Débora Lemos\n41 99123-0000")
        self.assertEqual(achado.nome, "Débora Lemos")
        self.assertIn("voluntária do Natal Solidário", achado.cargo)

    def test_remetente_que_nao_e_gente_nao_vira_nome(self):
        self.assertIsNone(self.pedido(corpo="Pedimos RG no dia 3.", remetente="Gabinete SESP"))


class QuantidadeTests(SimpleTestCase):
    def quantidade(self, texto, dias=1):
        achado = quantidade_de_cin(texto, dias=dias)
        return achado.valor if achado else None

    def test_por_dia_vezes_os_dias(self):
        self.assertEqual(self.quantidade("Estimamos 300 atendimentos por dia.", dias=2), 600)
        self.assertEqual(self.quantidade("Em três sábados. Previsão de 50 carteiras por sábado."), 150)

    def test_publico_nao_e_cin(self):
        self.assertIsNone(self.quantidade("Esperamos cerca de 400 mulheres de 15 municípios."))
        texto = "Pedimos a emissão de RG. Público estimado: 600 pessoas, das quais cerca de 120 vão precisar do documento."
        self.assertEqual(self.quantidade(texto), 120)

    def test_pessoas_para_documento(self):
        self.assertEqual(self.quantidade("São 60 pessoas agendadas para fazer a carteira de identidade."), 60)
        self.assertEqual(self.quantidade("fazer carteira de identidade pros idosos, acho q uns 60."), 60)
        self.assertEqual(self.quantidade("vamos distribuir 300 senhas para a emissão da carteira."), 300)
        self.assertIsNone(self.quantidade("Seremos 35 alunos e 2 professores."))

    def test_acoes_passadas_nao_contam(self):
        self.assertIsNone(self.quantidade("Nas ações de 2025 foram cerca de 200 carteiras cada."))


class TextoDoPedidoTests(SimpleTestCase):
    def test_negacao_tema_e_servico_de_outro_orgao_somem(self):
        self.assertNotIn("RG", texto_do_pedido("Só orientação jurídica. Não precisamos de emissão de RG."))
        self.assertNotIn("Carteira", texto_do_pedido("Oficina sobre documentos falsos e a nova Carteira de Identidade."))
        self.assertNotIn("jurídica", texto_do_pedido("A orientação jurídica ficará por conta da Defensoria."))

    def test_tema_acaba_onde_volta_o_pedido(self):
        texto = texto_do_pedido("Uma palestra sobre medidas protetivas e também a emissão de carteira de identidade.")
        self.assertIn("emissão de carteira de identidade", texto)
        self.assertNotIn("medidas", texto)
