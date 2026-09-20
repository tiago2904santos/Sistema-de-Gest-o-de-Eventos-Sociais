"""O segundo fluxo do pedido: mandar um recado e sair com os documentos montados.

É aqui que mora a garantia central do assistente — entre o pedido e a gravação
existe sempre um resumo e um "confirmar", e o que o sistema entendeu aparece
resolvido (nome completo, município com UF, data por extenso) antes disso.
"""

from django.test import TestCase

from assistente.llm.deterministico import InterpretadorDeterministico
from assistente.models import AcaoPendente
from assistente.orquestrador import responder

from .fixtures import criar_geografia, criar_pessoas, criar_usuario

PEDIDO = (
    "faça os documentos para um evento em Maringá dia 18/11/2026, "
    "vai o João Silva com o motorista Pereira"
)
PEDIDO_AMBIGUO = (
    "faça os documentos para um evento em Maringá dia 18/11/2026, vai o Silva"
)


class PreparoDeViagem(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.geo = criar_geografia()
        self.pessoas = criar_pessoas()
        self.interpretador = InterpretadorDeterministico()
        self.conversa = None

    def _dizer(self, texto):
        resposta = responder(
            self.usuario, texto, conversa=self.conversa, interpretador=self.interpretador
        )
        self.conversa = resposta.conversa
        return resposta

    def _ate_a_confirmacao(self):
        self._dizer(PEDIDO)
        self._dizer("Curitiba")  # município sede
        return self._dizer("Operação PCPR Mais Perto")  # motivo

    def test_extrai_o_que_foi_dito_e_pergunta_so_o_que_faltou(self):
        resposta = self._dizer(PEDIDO)
        self.assertIn("De qual município a equipe sai?", resposta.texto)
        acao = AcaoPendente.objects.get()
        self.assertEqual(acao.rascunho["destino"], self.geo["maringa"].pk)
        self.assertEqual(acao.rascunho["data_inicio"], "2026-11-18")
        self.assertEqual(acao.rascunho["servidores"], [self.pessoas["joao"].pk])
        self.assertEqual(acao.rascunho["motorista"], self.pessoas["pereira"].pk)

    def test_o_resumo_mostra_os_valores_resolvidos(self):
        resposta = self._ate_a_confirmacao()
        self.assertTrue(resposta.aguardando_confirmacao)
        self.assertIn("Destino: MARINGÁ/PR", resposta.texto)
        self.assertIn("Data de início: 18/11/2026", resposta.texto)
        self.assertIn("Servidores: JOÃO SILVA", resposta.texto)
        self.assertIn("Motorista: CARLOS PEREIRA", resposta.texto)
        self.assertIn("Confirma?", resposta.texto)

    def test_nada_e_gravado_antes_da_confirmacao(self):
        from viagens_oficios.models import Oficio
        from viagens_viagem.models import Viagem

        self._ate_a_confirmacao()
        self.assertFalse(Viagem.objects.exists())
        self.assertFalse(Oficio.objects.exists())
        self.assertEqual(AcaoPendente.objects.get().status, AcaoPendente.Status.AGUARDANDO)

    def test_confirmar_cria_viagem_roteiro_oficio_e_termo(self):
        from viagens_oficios.models import Oficio
        from viagens_roteiros.models import Roteiro
        from viagens_termos.models import TermoAutorizacao
        from viagens_viagem.models import Viagem

        self._ate_a_confirmacao()
        resposta = self._dizer("confirmar")

        viagem = Viagem.objects.get()
        self.assertEqual(viagem.destino_municipio, self.geo["maringa"])
        self.assertEqual(viagem.motivo, "Operação PCPR Mais Perto")
        self.assertEqual(viagem.status, Viagem.STATUS_EM_PREPARACAO)

        roteiro = Roteiro.objects.get()
        self.assertEqual(roteiro.origem_municipio, self.geo["curitiba"])
        self.assertEqual(roteiro.destinos.get().municipio, self.geo["maringa"])

        oficio = Oficio.objects.get()
        self.assertEqual(oficio.status, Oficio.STATUS_RASCUNHO)
        self.assertEqual(list(oficio.servidores.all()), [self.pessoas["joao"]])
        self.assertEqual(oficio.motorista, self.pessoas["pereira"])
        # Rascunho não gasta número: a numeração é reservada na finalização.
        self.assertIsNone(oficio.numero)

        self.assertTrue(TermoAutorizacao.objects.exists())
        self.assertIn(f"Viagem #{viagem.pk}", resposta.texto)
        self.assertEqual(AcaoPendente.objects.get().status, AcaoPendente.Status.CONFIRMADA)

    def test_confirmacao_fica_registrada_na_auditoria(self):
        from auditoria.models import LogAuditoria

        self._ate_a_confirmacao()
        self._dizer("confirmar")
        log = LogAuditoria.objects.get(acao="assistente:preparar_viagem")
        self.assertEqual(log.usuario, self.usuario)

    def test_cancelar_nao_grava_nada(self):
        from viagens_viagem.models import Viagem

        self._ate_a_confirmacao()
        resposta = self._dizer("cancelar")
        self.assertIn("Nada foi gravado", resposta.texto)
        self.assertFalse(Viagem.objects.exists())
        self.assertEqual(AcaoPendente.objects.get().status, AcaoPendente.Status.CANCELADA)

    def test_resposta_ambigua_na_confirmacao_nao_executa(self):
        from viagens_viagem.models import Viagem

        self._ate_a_confirmacao()
        resposta = self._dizer("acho que sim, né")
        self.assertIn("Ainda não gravei nada", resposta.texto)
        self.assertFalse(Viagem.objects.exists())


class DesambiguacaoDePessoa(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.geo = criar_geografia()
        self.pessoas = criar_pessoas()
        self.interpretador = InterpretadorDeterministico()
        self.conversa = None

    def _dizer(self, texto):
        resposta = responder(
            self.usuario, texto, conversa=self.conversa, interpretador=self.interpretador
        )
        self.conversa = resposta.conversa
        return resposta

    def test_sobrenome_repetido_vira_pergunta_com_menu(self):
        resposta = self._dizer(PEDIDO_AMBIGUO)
        self.assertIn("mais de um servidor", resposta.texto)
        self.assertEqual(len(resposta.opcoes), 2)
        self.assertIn("JOÃO SILVA", resposta.texto)
        self.assertIn("MARCOS SILVA", resposta.texto)

    def test_o_resto_do_pedido_sobrevive_a_pergunta(self):
        """O motorista dito no pedido não pode sumir porque o nome era ambíguo.

        Regressão: a varredura parava na primeira ambiguidade e o que vinha
        depois era descartado — o resumo saía sem motorista e ninguém era
        avisado disso.
        """
        self._dizer(PEDIDO_AMBIGUO + " com o motorista Pereira")
        self._dizer("1")
        acao = AcaoPendente.objects.get()
        self.assertEqual(acao.rascunho["servidores"], [self.pessoas["joao"].pk])
        self.assertEqual(acao.rascunho["motorista"], self.pessoas["pereira"].pk)

    def test_escolher_pelo_numero_resolve(self):
        self._dizer(PEDIDO_AMBIGUO)
        self._dizer("2")
        acao = AcaoPendente.objects.get()
        self.assertEqual(acao.rascunho["servidores"], [self.pessoas["marcos"].pk])

    def test_nome_desconhecido_e_dito_em_voz_alta(self):
        """Nome fora do cadastro não some do pedido — vira pergunta.

        Descartá-lo em silêncio faria a pessoa ler um resumo sem aquele
        servidor e, na pressa, confirmar assim mesmo.
        """
        resposta = self._dizer(
            "faça os documentos para um evento em Maringá dia 18/11/2026, vai o Ferreira"
        )
        self.assertIn("Não achei nenhum servidor", resposta.texto)
        self.assertIn("Ferreira", resposta.texto)


class PermissaoDeEscrita(TestCase):
    def test_quem_so_consulta_nao_prepara(self):
        from viagens_viagem.models import Viagem

        usuario = criar_usuario("consulta", pode_escrever=False)
        criar_geografia()
        criar_pessoas()
        resposta = responder(usuario, PEDIDO, interpretador=InterpretadorDeterministico())
        self.assertIn("fora do seu acesso", resposta.texto)
        self.assertFalse(Viagem.objects.exists())
        self.assertFalse(AcaoPendente.objects.exists())
