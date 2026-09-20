"""O primeiro fluxo do pedido: perguntar quem vai a um lugar, num período."""

import datetime as dt

from django.test import TestCase

from assistente.llm.deterministico import InterpretadorDeterministico
from assistente.models import AcaoPendente, Mensagem
from assistente.orquestrador import responder

from .fixtures import (
    criar_geografia,
    criar_pessoas,
    criar_usuario,
    criar_viagem_com_equipe,
    setembro_do_proximo,
)


class ConsultaDeDeslocamentos(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.geo = criar_geografia()
        self.pessoas = criar_pessoas()
        self.interpretador = InterpretadorDeterministico()
        self.data = setembro_do_proximo()
        criar_viagem_com_equipe(
            self.geo["maringa"],
            self.data,
            [self.pessoas["joao"], self.pessoas["marcos"]],
            motorista=self.pessoas["pereira"],
        )
        # Ruído deliberado: outra cidade, e o mesmo mês. Não pode aparecer.
        criar_viagem_com_equipe(self.geo["curitiba"], self.data, [self.pessoas["joao"]])

    def _perguntar(self, texto):
        return responder(self.usuario, texto, interpretador=self.interpretador)

    def test_quem_vai_para_o_destino_no_mes(self):
        resposta = self._perguntar("quem vai para Maringá em setembro?")
        self.assertEqual(resposta.ferramenta, "consultar_deslocamentos")
        self.assertIn("JOÃO SILVA", resposta.texto)
        self.assertIn("MARCOS SILVA", resposta.texto)
        self.assertIn("CARLOS PEREIRA", resposta.texto)
        self.assertIn("(motorista)", resposta.texto)

    def test_nao_mistura_quem_vai_para_outro_destino(self):
        resposta = self._perguntar("quem vai para Curitiba em setembro?")
        self.assertIn("JOÃO SILVA", resposta.texto)
        self.assertNotIn("MARCOS SILVA", resposta.texto)

    def test_periodo_sem_ninguem_responde_que_nao_ha(self):
        outro_ano = self.data.year + 3
        resposta = self._perguntar(f"quem vai para Maringá em setembro de {outro_ano}?")
        self.assertIn("Ninguém escalado", resposta.texto)

    def test_municipio_fora_do_cadastro_nao_vira_palpite(self):
        resposta = self._perguntar("quem vai para Xanxerê em setembro?")
        self.assertIn("Não encontrei o município", resposta.texto)

    def test_consulta_nao_cria_acao_nem_pede_confirmacao(self):
        self._perguntar("quem vai para Maringá em setembro?")
        self.assertFalse(AcaoPendente.objects.exists())

    def test_a_conversa_fica_gravada_com_a_procedencia(self):
        resposta = self._perguntar("quem vai para Maringá em setembro?")
        mensagens = list(resposta.conversa.mensagens.all())
        self.assertEqual(mensagens[0].autor, Mensagem.Autor.PESSOA)
        self.assertEqual(mensagens[1].autor, Mensagem.Autor.ASSISTENTE)
        self.assertEqual(mensagens[1].ferramenta, "consultar_deslocamentos")

    def test_pergunta_sobre_pendencias(self):
        resposta = self._perguntar("o que está pendente?")
        self.assertEqual(resposta.ferramenta, "consultar_pendencias")

    def test_pergunta_que_nao_casa_com_nada_oferece_ajuda(self):
        resposta = self._perguntar("bom dia, tudo bem?")
        self.assertIn("Posso consultar e preparar", resposta.texto)
        self.assertEqual(resposta.ferramenta, "")


class ConsultaSemPermissao(TestCase):
    def test_sem_o_modulo_o_assistente_nao_oferece_nada(self):
        usuario = criar_usuario("visitante", com_modulo=False, pode_escrever=False)
        resposta = responder(
            usuario, "quem vai para Maringá?", interpretador=InterpretadorDeterministico()
        )
        self.assertIn("não tem acesso a nenhum módulo", resposta.texto)
