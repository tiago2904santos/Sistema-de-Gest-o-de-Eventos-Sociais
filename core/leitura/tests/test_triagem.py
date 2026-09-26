from django.test import SimpleTestCase

from core.leitura.mensagem import ler_texto_colado
from core.leitura.triagem import triar, triar_mensagem


class TriagemTests(SimpleTestCase):
    def primeiro(self, **kwargs):
        destinos = triar(**kwargs)
        self.assertTrue(destinos, kwargs)
        return destinos[0]

    def test_coffee_break(self):
        destino = self.primeiro(assunto="Solicitação de coffe break", corpo="Kit lanche e salgados para 80 pessoas.")
        self.assertEqual(destino.modulo, "coffee_break")
        self.assertIn("coffee break (assunto)", destino.sinais)

    def test_imprensa_pelo_dominio_e_pela_assinatura(self):
        destino = self.primeiro(
            assunto="Pedido de posicionamento",
            corpo="Gostaria de uma nota sobre o caso. Deadline às 17h.",
            assinatura="Fulano\nRepórter\nRedação",
            remetente_email="fulano@gazetadopovo.com.br",
        )
        self.assertEqual(destino.modulo, "atendimento_imprensa")
        self.assertIn("remetente de veículo de imprensa", destino.sinais)
        self.assertIn("assinatura de jornalista", destino.sinais)

    def test_nota_fiscal_nao_e_imprensa(self):
        destinos = triar(corpo="Segue a nota fiscal do coffee break.")
        self.assertEqual(destinos[0].modulo, "coffee_break")
        self.assertNotIn("atendimento_imprensa", [d.modulo for d in destinos])

    def test_publicacoes_da_pcpr(self):
        destino = self.primeiro(
            assunto="Release - Operação Exemplo",
            corpo="Para divulgação: prisão em flagrante e cumprimento de mandados.",
            remetente_email="delegacia@pc.pr.gov.br",
        )
        self.assertEqual(destino.modulo, "publicacoes")
        self.assertIn("remetente da PCPR", destino.sinais)

    def test_evento_social(self):
        destino = self.primeiro(assunto="Paraná em Ação", corpo="Pedimos a unidade móvel para emissão de RG no mutirão.")
        self.assertEqual(destino.modulo, "solicitacoes")

    def test_palestra(self):
        destino = self.primeiro(assunto="Solicitação de palestra", corpo="Para 120 alunos do Colégio Estadual, tema golpes.")
        self.assertEqual(destino.modulo, "demandas_eventos")
        self.assertGreaterEqual(destino.confianca, 0.8)

    def test_empate_baixa_a_confianca_e_mostra_os_dois(self):
        destinos = triar(corpo="Palestra na escola com coffee break para os alunos.")
        self.assertEqual({d.modulo for d in destinos[:2]}, {"demandas_eventos", "coffee_break"})
        self.assertLess(destinos[0].confianca, 0.8)

    def test_limita_aos_modulos_do_usuario(self):
        destinos = triar(assunto="Solicitação de palestra com coffee break", modulos=["coffee_break"])
        self.assertEqual([d.modulo for d in destinos], ["coffee_break"])

    def test_sem_sinal_nao_ha_destino(self):
        self.assertEqual(triar(assunto="Olá", corpo="Tudo bem?"), [])

    def test_a_partir_da_mensagem(self):
        mensagem = ler_texto_colado(
            "De: Ana <ana@colegio.pr.gov.br>\nEnviado em: 24/09/2026 10:00\nPara: ASCOM\n"
            "Assunto: RES: Palestra sobre golpes\n\nPara 80 alunos.\n\nAtt,\nAna\nPedagoga"
        )
        self.assertEqual(triar_mensagem(mensagem)[0].modulo, "demandas_eventos")


class SinaisNovosETriagemComMemoriaTests(SimpleTestCase):
    def test_identificacao_civil_e_evento_social_mesmo_com_escola_e_alunos(self):
        destino = triar(
            assunto="Programa Criança e Adolescente Protegidos – apoio institucional",
            corpo="Emissão da Carteira de Identidade Nacional (CIN) para estudantes da rede municipal; "
                  "426 alunos sem RG nas escolas das ilhas; identificação civil pelo Instituto de Identificação.",
        )[0]
        self.assertEqual(destino.modulo, "solicitacoes")
        self.assertIn("identificação civil", destino.sinais)

    def test_atendimento_in_loco_para_acamados(self):
        destino = triar(
            assunto="Solicitação de ação para emissão da Carteira de Identidade Nacional (CIN)",
            corpo="Atendimento in loco para regularização da documentação de identificação civil de 10 pacientes.",
        )[0]
        self.assertEqual(destino.modulo, "solicitacoes")

    def test_extras_da_memoria_entram_na_conta(self):
        destinos = triar(
            corpo="Bom dia, segue em anexo o ofício.",
            extras={"coffee_break": [(6.0, "3 pedidos anteriores deste remetente")]},
        )
        self.assertEqual(destinos[0].modulo, "coffee_break")
        self.assertIn("3 pedidos anteriores deste remetente", destinos[0].sinais)
        # Módulo desconhecido e peso zero são ignorados.
        self.assertEqual(triar(corpo="x", extras={"nada": [(9, "x")], "publicacoes": [(0, "y")]}), [])
