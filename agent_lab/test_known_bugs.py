"""Bugs de produto confirmados pelo laboratório e ainda abertos.

Cada teste descreve o comportamento CORRETO e está marcado com
``expectedFailure``: enquanto o bug existir, a suíte passa; quando alguém
corrigir, o teste "passa inesperadamente" e acusa — aí remova o decorator.
"""

import unittest

from django.contrib.auth import get_user_model
from django.test import TestCase

from agent_lab.seed import Semeador


class ExclusaoDeServidorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Semeador("small").executar()

    @unittest.expectedFailure
    def test_excluir_servidor_com_prestacao_e_bloqueado(self):
        """KP-00 (P1, perda de dado): `PrestacaoServidor.servidor` é CASCADE e a checagem
        `_dependencias_protegidas` só olha PROTECT/RESTRICT — excluir o servidor pela tela
        apaga em silêncio as prestações de contas dele."""
        from viagens_prestacoes.models import PrestacaoServidor

        ps = PrestacaoServidor.objects.select_related("servidor").first()
        self.assertIsNotNone(ps, "o seed small deveria criar prestações")
        self.client.force_login(get_user_model().objects.get(username="lab.viagens_gestor"))
        self.client.post(f"/viagens/cadastros/servidores/{ps.servidor_id}/excluir/")
        self.assertTrue(PrestacaoServidor.objects.filter(pk=ps.pk).exists())
