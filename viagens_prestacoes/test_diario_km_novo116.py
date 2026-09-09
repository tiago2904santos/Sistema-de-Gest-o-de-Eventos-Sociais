"""`NOVO-116` — km invertido no diário recusa na tela, e não derruba edição válida.

A `0033` pôs o `diario_trecho_km_ordenado` no banco sem tocar em quem escreve. O
`NOVO-36` já tinha registrado o preço disso: *"pôr o `CHECK` antes de consertar o
produtor troca dado silenciosamente errado por erro 500 numa tela de uso diário"*. Era
exatamente o caso aqui, por dois caminhos:

1. **O 500.** `salvar_autosave_do_diario` gravava direto, sem `full_clean`, e nenhuma
   das duas views de autosave tratava `IntegrityError`. Km invertido virava 500 sem
   mensagem, num campo que o operador digita à mão.
2. **A edição válida derrubada.** O laço gravava um `UPDATE` **por campo sujo**, e o
   payload não promete ordem. Corrigir uma linha de `100→200` para `5000→6000` passava
   por `km_inicial=5000` contra o `km_final=200` ainda não gravado: violação no meio do
   caminho, com estado final perfeitamente válido. Intermitente por ordem de dicionário
   — o pior tipo de 500 para reproduzir.

O segundo é o que dá o teste mais valioso do arquivo
(`test_trocar_os_dois_km_para_valores_maiores_grava`): ele não fala de dado inválido
nenhum, e reprovava do mesmo jeito.

O `NOVO-107` tornou o roteiro parte do estado padrão da fixture, como em produção.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
import json
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes.models import DiarioBordo
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin
MENSAGEM = 'O km final não pode ser menor que o km inicial.'

class KmDoDiarioNoAutosaveTests(PrestacaoFixturesMixin, TestCase):
    """O caminho da tela: JSON, e a resposta que o `autosave.js` sabe exibir."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=81)
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        self.diario, _ = DiarioBordo.objects.get_or_create(prestacao=self.prestacao)
        self.client.get(reverse('viagens_prestacoes:diario_servidor', args=[self.ps.pk]))
        self.assertTrue(self._linhas(), 'sem linha de diário nada aqui mediria')

    def _linhas(self):
        return list(self.diario.trechos.order_by('ordem', 'pk'))

    def autosave(self, **campos):
        return self.client.post(reverse('viagens_prestacoes:diario_autosave', args=[self.diario.pk]), data=json.dumps({'model': 'diario_bordo', 'object_id': str(self.diario.pk), 'dirty_fields': list(campos), 'fields': campos}), content_type='application/json')

    def test_km_invertido_responde_400_com_mensagem(self):
        """O defeito: isto era 500, e o operador não via texto nenhum."""
        resposta = self.autosave(**{'form-0-km_inicial': '5.000', 'form-0-km_final': '215'})
        self.assertEqual(resposta.status_code, 400)
        corpo = json.loads(resposta.content)
        self.assertFalse(corpo['ok'])
        self.assertIn(MENSAGEM, corpo['message'])

    def test_km_invertido_nao_grava_nada(self):
        """Recusar é meia garantia; a outra é a linha ficar como estava."""
        self.autosave(**{'form-0-km_inicial': '5.000', 'form-0-km_final': '215'})
        linha = self._linhas()[0]
        self.assertIsNone(linha.km_inicial)
        self.assertIsNone(linha.km_final)

    def test_trocar_os_dois_km_para_valores_maiores_grava(self):
        """A edição válida que o laço por campo derrubava.

        Nada aqui é inválido: `100→200` vira `5000→6000`. O que reprovava era o estado
        intermediário `km_inicial=5000` contra o `km_final=200` ainda no banco.
        """
        self.autosave(**{'form-0-km_inicial': '100', 'form-0-km_final': '200'})
        resposta = self.autosave(**{'form-0-km_inicial': '5.000', 'form-0-km_final': '6.000'})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(json.loads(resposta.content)['ok'])
        linha = self._linhas()[0]
        self.assertEqual(linha.km_inicial, 5000)
        self.assertEqual(linha.km_final, 6000)

    def test_km_igual_e_aceito(self):
        """Trecho sem deslocamento tem os dois iguais — é a razão do `gte`."""
        resposta = self.autosave(**{'form-0-km_inicial': '800', 'form-0-km_final': '800'})
        self.assertEqual(resposta.status_code, 200)
        linha = self._linhas()[0]
        self.assertEqual(linha.km_final, 800)

    def test_km_final_menor_contra_o_inicial_ja_gravado(self):
        """O par não precisa vir sujo junto: um campo só, contra o que está no banco."""
        self.autosave(**{'form-0-km_inicial': '5.000'})
        resposta = self.autosave(**{'form-0-km_final': '215'})
        self.assertEqual(resposta.status_code, 400)
        self.assertIn(MENSAGEM, json.loads(resposta.content)['message'])
        self.assertIsNone(self._linhas()[0].km_final)

    def test_rota_por_servidor_recusa_igual(self):
        """As duas rotas de autosave divergem em escopo de status, não em validação."""
        resposta = self.client.post(reverse('viagens_prestacoes:diario_servidor_autosave', args=[self.ps.pk]), data=json.dumps({'model': 'diario_bordo', 'object_id': str(self.diario.pk), 'dirty_fields': ['form-0-km_inicial', 'form-0-km_final'], 'fields': {'form-0-km_inicial': '900', 'form-0-km_final': '300'}}), content_type='application/json')
        self.assertEqual(resposta.status_code, 400)
        self.assertIn(MENSAGEM, json.loads(resposta.content)['message'])

class KmDoDiarioNoFormsetTests(PrestacaoFixturesMixin, TestCase):
    """O caminho sem JS: o formset tem de dizer a mesma coisa, com o mesmo texto."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=82)
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        self.diario, _ = DiarioBordo.objects.get_or_create(prestacao=self.prestacao)
        self.client.get(reverse('viagens_prestacoes:diario_servidor', args=[self.ps.pk]))
        self.linhas = list(self.diario.trechos.order_by('ordem', 'pk'))
        self.assertTrue(self.linhas, 'sem linha de diário nada aqui mediria')

    def postar(self, km_inicial, km_final):
        dados = {'form-TOTAL_FORMS': str(len(self.linhas)), 'form-INITIAL_FORMS': str(len(self.linhas)), 'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000'}
        for i, linha in enumerate(self.linhas):
            dados[f'form-{i}-id'] = str(linha.pk)
            dados[f'form-{i}-km_inicial'] = km_inicial
            dados[f'form-{i}-km_final'] = km_final
            dados[f'form-{i}-abastecimento'] = 'sim'
        return self.client.post(reverse('viagens_prestacoes:diario_servidor', args=[self.ps.pk]), dados)

    def test_km_invertido_reprova_com_texto_legivel(self):
        """Antes saía `Restrição "diario_trecho_km_ordenado" foi violada.` na tela."""
        resposta = self.postar('5.000', '215')
        self.assertEqual(resposta.status_code, 200, 'reprovou e deve reexibir o form')
        formset = resposta.context['formset']
        self.assertFalse(formset.is_valid())
        self.assertIn(MENSAGEM, str(formset.errors))
        self.assertNotIn('diario_trecho_km_ordenado', str(formset.errors))

    def test_km_invertido_nao_grava(self):
        self.postar('5.000', '215')
        linha = self.linhas[0]
        linha.refresh_from_db()
        self.assertIsNone(linha.km_inicial)
