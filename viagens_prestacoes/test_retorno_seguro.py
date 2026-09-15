"""BE-08 — `?next=` de prestações precisa passar por `core/retorno`.

`core/retorno.py` existe exatamente para isto e explica o risco no próprio
docstring: `?next=` é entrada do usuário que vira `Location:` de um redirect, e
sem validação de host é *open redirect*. O módulo não era usado em
`viagens_prestacoes`: funções liam `request.POST.get("next")` e passavam
direto para `redirect()`.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin
EXTERNO = 'https://exemplo-externo.invalido/coleta'

class RetornoSeguroTests(PrestacaoFixturesMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.ps = self.fixture.prestacoes_servidor[0]

    def _assert_nao_sai_do_dominio(self, response):
        destino = response['Location']
        self.assertFalse(destino.startswith('http://') or destino.startswith('https://'), msg=f'redirect saiu do domínio: {destino}')

    def test_arquivar_servidor_nao_segue_next_externo(self):
        response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_arquivar', args=[self.ps.pk]), {'next': EXTERNO})
        self.assertEqual(response.status_code, 302)
        self._assert_nao_sai_do_dominio(response)

    def test_next_interno_continua_sendo_honrado(self):
        """A proteção não pode custar o recurso: `next` do próprio host segue valendo."""
        interno = reverse('viagens_prestacoes:documentos_servidor', args=[self.ps.pk])
        response = self.client.post(reverse('viagens_prestacoes:prestacao_servidor_arquivar', args=[self.ps.pk]), {'next': interno})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], interno)
