"""Regras do "Preencher com um e-mail" da palestra: quem pede, local, público, canal, temas."""

from django.test import TestCase

from core.leitura.mensagem import ler_texto_colado

from . import preenchimento
from .models import CanalSolicitacao, Palestrante, Tema, TipoEventoPalestra
from .publico import publico_no_texto
from .solicitante import sem_nomes_de_instituicao


def _valor(texto, campo):
    sugestao = preenchimento.sugestoes(ler_texto_colado(texto)).get(campo)
    return sugestao.valor if sugestao is not None else None


class SolicitanteTests(TestCase):
    def test_quem_se_apresenta_pela_instituicao(self):
        texto = "Bom dia! Sou pedagoga do Colégio Estadual Santa Rosa, de Cruz Machado. Queremos uma palestra sobre drogas."
        self.assertIn("Colégio Estadual Santa Rosa", _valor(texto, "solicitante"))

    def test_a_instituicao_que_pede(self):
        texto = "Prezados,\n\nA Cerâmica Itaqui, de Campo Largo, gostaria de uma palestra sobre trânsito."
        self.assertIn("Cerâmica Itaqui", _valor(texto, "solicitante"))

    def test_pedido_encaminhado_e_do_original(self):
        texto = (
            "Senhores,\n\nEncaminho o pedido do Rotary Club de Pato Branco para palestra.\n\n"
            "Contato: secretaria@rotary-exemplo.org.br - (46) 99111-2323"
        )
        self.assertEqual(_valor(texto, "solicitante"), "Rotary Club de Pato Branco")
        self.assertEqual(_valor(texto, "email"), "secretaria@rotary-exemplo.org.br")
        self.assertEqual(_valor(texto, "telefone"), "(46) 99111-2323")

    def test_linha_toda_minuscula(self):
        texto = "oi td bem sou da escola estadual pe anchieta de ivai\nprecisamos de palestra sobre drogas"
        self.assertIn("escola estadual pe anchieta", _valor(texto, "solicitante"))


class LocalTests(TestCase):
    def test_o_colegio_citado_da_nome_ao_local(self):
        texto = (
            "O Colégio Estadual Presidente Kennedy solicita palestra sobre drogas no dia 22/10, "
            "às 19h, no auditório do colégio (Rua X, 100)."
        )
        self.assertEqual(_valor(texto, "local"), "auditório do Colégio Estadual Presidente Kennedy")

    def test_nome_do_lugar_que_quebra_a_linha(self):
        texto = "A Câmara Municipal de Guaíra convida para palestra no dia 9/10, às 8h30, no Plenário\nda Câmara, Rua Y, 126."
        self.assertEqual(_valor(texto, "local"), "Plenário da Câmara")

    def test_sem_lugar_dito_vale_a_escola_dos_alunos(self):
        texto = "Solicitamos palestra sobre drogas para os alunos do 5º ano da Escola Municipal Nilo Berlitz, dia 18/11."
        self.assertEqual(_valor(texto, "local"), "Escola Municipal Nilo Berlitz")


class PublicoTests(TestCase):
    def test_numero_declarado(self):
        self.assertEqual(publico_no_texto("Esperamos cerca de 200 alunos.").valor, 200)
        self.assertEqual(publico_no_texto("Esperamos umas 150 mulheres.").valor, 150)
        self.assertEqual(publico_no_texto("público estimado de 15 mil pessoas").valor, 15000)

    def test_conta_de_turmas_e_quilometro_ficam_fora(self):
        self.assertIsNone(publico_no_texto("3 turmas de 35"))
        self.assertEqual(publico_no_texto("Local: Rodovia PR-151, km 212\nPúblico: 130 motoristas").valor, 130)


class CanalEventoTemaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.transito = Tema.objects.create(nome="Trânsito")
        cls.golpes = Tema.objects.create(nome="Golpes e fraudes")
        cls.juliana = Palestrante.objects.create(nome="Juliana Bittencourt Mehl")
        cls.everton = Palestrante.objects.create(nome="Everton Scheffer")

    def test_recado_de_telefone_e_atendimento_presencial(self):
        recado = "RECADO - 14/10/2026 - 15h20\n\nLigou a Sra. Joana, secretária da APAE, pedindo palestra."
        self.assertEqual(_valor(recado, "canal_solicitacao"), CanalSolicitacao.TELEFONE)
        visita = "ATENDIMENTO PRESENCIAL - 03/11/2026\n\nCompareceu o presidente do Lions pedindo palestra."
        self.assertEqual(_valor(visita, "canal_solicitacao"), CanalSolicitacao.PRESENCIAL)

    def test_sessao_solene_e_evento(self):
        texto = "A CÂMARA MUNICIPAL CONVIDA A POLÍCIA CIVIL PARA A SESSÃO\nSOLENE DE ENTREGA DE MOÇÕES."
        self.assertEqual(_valor(texto, "evento"), TipoEventoPalestra.EVENTO)

    def test_tema_no_nome_da_instituicao_nao_conta(self):
        texto = "A Secretaria Municipal de Segurança e Trânsito realizará o 1º Seminário e convida a Polícia Civil."
        self.assertNotIn("Trânsito", sem_nomes_de_instituicao(texto))
        self.assertIsNone(_valor(texto, "temas"))

    def test_tema_pela_primeira_parte_da_enumeracao(self):
        texto = "quero pedir uma palestra sobre golpe de telefone e whatsapp pros idoso"
        self.assertEqual(_valor(texto, "temas"), [self.golpes])

    def test_palestrante_abreviado_ou_pelo_cargo(self):
        self.assertEqual(_valor("Se possível, com a Dra. Juliana Mehl.", "palestrantes"), [self.juliana])
        self.assertEqual(_valor("Gostamos da palestra do investigador Everton.", "palestrantes"), [self.everton])
        # Nome solto (a destinatária, o remetente) não é pedido de palestrante.
        self.assertIsNone(_valor("Oi Everton, tudo bem? Segue o pedido.", "palestrantes"))


class HoraDaOpcaoEscolhidaTests(TestCase):
    def test_a_hora_e_a_do_dia_escolhido_na_conversa(self):
        texto = (
            "Pode ser a segunda opção, dia 20/11. Obrigada!\n\n"
            "Em qui., 5 de nov. de 2026 às 16:20, ASCOM <ascom@pc.pr.gov.br> escreveu:\n"
            "> Podemos atender no dia 19/11 às 9h ou no dia 20/11 às 14h. Qual prefere?\n"
        )
        self.assertEqual(f"{_valor(texto, 'hora_inicio'):%H:%M}", "14:00")
