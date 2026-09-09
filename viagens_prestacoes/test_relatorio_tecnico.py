"""Fatia 4/6 de T-01 — relatório técnico e valor de diária por servidor.

Primeira fatia em que **dinheiro** aparece. É a rede que a Etapa 3 vai precisar:
o `N-01` (tabela de diárias fixada no código, sem vigência) mexe justamente no
valor que chega aqui, e sem estes testes a mudança seria feita no escuro.

O valor de diária por servidor era **texto livre** — `CharField` sem validação,
e qualquer string chegava ao documento e ao texto de WhatsApp (`NOVO-10`).
Estes testes caracterizaram o defeito antes de existir a correção; hoje
afirmam a regra: o valor é dinheiro, é positivo e **nunca passa do liberado**.

Continua caracterizado, sem juízo de valor: os campos de custeio do RT têm dois
regimes — os de lista fechada só aceitam valor do conjunto permitido, os livres
aceitam qualquer texto.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
import json
from decimal import Decimal
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_oficios.models import Oficio
from viagens_prestacoes.models import RelatorioTecnico
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin
from viagens_roteiros.models import Roteiro

class DiariaOverrideTests(PrestacaoFixturesMixin, TestCase):
    """O valor que difere do padrão, por servidor."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.ps = self.fixture.prestacoes_servidor[0]
        self.relatorio = RelatorioTecnico.objects.create(prestacao=self.fixture.prestacao)

    def autosave_rt(self, relatorio=None, **campos):
        relatorio = relatorio or self.relatorio
        payload = {'model': 'relatorio_tecnico', 'object_id': str(relatorio.pk), 'dirty_fields': list(campos), 'fields': campos}
        return self.client.post(reverse('viagens_prestacoes:rt_autosave', args=[relatorio.pk]), data=json.dumps(payload), content_type='application/json')

    def test_override_persiste_por_servidor_sem_afetar_os_demais(self):
        outro_servidor = self.criar_servidor('Segundo Servidor')
        dupla = self.criar_prestacao(numero=2, servidores=[self.ps.servidor, outro_servidor])
        relatorio = RelatorioTecnico.objects.create(prestacao=dupla.prestacao)
        ps_a, ps_b = dupla.prestacoes_servidor
        self.autosave_rt(relatorio, **{f'ps-{ps_a.pk}-diaria_valor_override': '  350,00  '})
        ps_a.refresh_from_db()
        ps_b.refresh_from_db()
        self.assertEqual(ps_a.diaria_valor_override, Decimal('350.00'))
        self.assertIsNone(ps_b.diaria_valor_override)

    def test_texto_que_nao_e_valor_e_recusado_e_nada_e_gravado(self):
        """`NOVO-10` corrigido: o que não é número não vira valor de diária.

        Era o defeito mais direto do módulo — um erro de digitação virava o
        valor impresso no relatório técnico do servidor e no texto de WhatsApp,
        sem nada avisar. O autosave agora responde 400 e não grava.
        """
        for entrada in ('abc', 'R$ mil reais', '-90', '350,00,00'):
            with self.subTest(entrada=entrada):
                response = self.autosave_rt(**{f'ps-{self.ps.pk}-diaria_valor_override': entrada})
                self.assertEqual(response.status_code, 400)
                self.assertIn(f'ps-{self.ps.pk}-diaria_valor_override', response.json()['errors'])
                self.ps.refresh_from_db()
                self.assertIsNone(self.ps.diaria_valor_override)

    def test_valor_com_anotacao_guarda_numero_e_texto_separados(self):
        """Uma caixa na tela, duas colunas no banco.

        O operador escreve "R$ 87,00 (saque)" porque o caixa não entrega
        centavos. O número passa a ser validável; a explicação continua indo
        para o documento.
        """
        self.autosave_rt(**{f'ps-{self.ps.pk}-diaria_valor_override': 'R$ 87,00 (saque)'})
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.diaria_valor_override, Decimal('87.00'))
        self.assertEqual(self.ps.diaria_valor_override_observacao, '(saque)')

    def test_valor_recebido_nao_pode_passar_do_liberado(self):
        """A regra que o campo existia para respeitar e nunca respeitou.

        O servidor pode receber menos do que foi liberado — sacar 87,00 de
        87,17, porque moeda não sai do caixa. Mais do que o liberado, nunca.
        """
        roteiro = Roteiro.objects.create(valor_diarias=Decimal('87.17'))
        Oficio.objects.filter(pk=self.fixture.oficio.pk).update(roteiro=roteiro)
        recusado = self.autosave_rt(**{f'ps-{self.ps.pk}-diaria_valor_override': 'R$ 90,00'})
        self.assertEqual(recusado.status_code, 400)
        self.ps.refresh_from_db()
        self.assertIsNone(self.ps.diaria_valor_override)
        for aceito in ('R$ 87,00', 'R$ 87,17'):
            with self.subTest(valor=aceito):
                self.autosave_rt(**{f'ps-{self.ps.pk}-diaria_valor_override': aceito})
                self.ps.refresh_from_db()
                self.assertIsNotNone(self.ps.diaria_valor_override)

    def test_o_documento_continua_imprimindo_valor_e_anotacao_juntos(self):
        """A separação é interna: o RT sai igual ao que saía antes.

        Se esta asserção quebrar, a migração mudou documento assinado — que é
        exatamente o que ela não pode fazer.
        """
        from viagens_prestacoes.services import build_relatorio_tecnico_context
        self.autosave_rt(**{f'ps-{self.ps.pk}-diaria_valor_override': 'R$ 87,00 (saque)'})
        self.ps.refresh_from_db()
        self.relatorio.refresh_from_db()
        contexto = build_relatorio_tecnico_context(self.relatorio, self.ps)
        self.assertEqual(contexto['diaria'], 'R$87,00 (saque)')

    def test_override_em_branco_volta_a_usar_o_valor_compartilhado(self):
        self.autosave_rt(**{f'ps-{self.ps.pk}-diaria_valor_override': '500,00'})
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.diaria_valor_override, Decimal('500.00'))
        self.autosave_rt(**{f'ps-{self.ps.pk}-diaria_valor_override': '   '})
        self.ps.refresh_from_db()
        self.assertIsNone(self.ps.diaria_valor_override)

    def test_override_nao_alcanca_servidor_de_outra_prestacao(self):
        """O `filter(prestacao=prestacao)` impede escrita cruzada entre ofícios."""
        vizinha = self.criar_prestacao(numero=3)
        ps_vizinho = vizinha.prestacoes_servidor[0]
        self.autosave_rt(**{f'ps-{ps_vizinho.pk}-diaria_valor_override': '999,00'})
        ps_vizinho.refresh_from_db()
        self.assertIsNone(ps_vizinho.diaria_valor_override)

class RelatorioTecnicoCamposTests(PrestacaoFixturesMixin, TestCase):
    """Os campos do RT: texto livre e custeio de lista fechada."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=1)
        self.relatorio = RelatorioTecnico.objects.create(prestacao=self.fixture.prestacao)

    def autosave_rt(self, **campos):
        payload = {'model': 'relatorio_tecnico', 'object_id': str(self.relatorio.pk), 'dirty_fields': list(campos), 'fields': campos}
        return self.client.post(reverse('viagens_prestacoes:rt_autosave', args=[self.relatorio.pk]), data=json.dumps(payload), content_type='application/json')

    def test_campos_narrativos_persistem_normalizados(self):
        self.autosave_rt(motivo='  Operação   conjunta  ', atividade='Fiscalização', conclusao='Concluída')
        self.relatorio.refresh_from_db()
        self.assertEqual(self.relatorio.motivo, 'Operação conjunta')
        self.assertEqual(self.relatorio.atividade, 'Fiscalização')
        self.assertEqual(self.relatorio.conclusao, 'Concluída')

    def test_campo_fora_da_lista_permitida_e_ignorado(self):
        """`filter_allowed_fields` é a fronteira: só passa o que está declarado."""
        self.autosave_rt(motivo='Guardado', campo_inventado='Ignorado')
        self.relatorio.refresh_from_db()
        self.assertEqual(self.relatorio.motivo, 'Guardado')
        self.assertFalse(hasattr(self.relatorio, 'campo_inventado'))

    def test_campo_nao_marcado_como_sujo_nao_e_gravado(self):
        """O autosave só grava o que o formulário declarou alterado."""
        payload = {'model': 'relatorio_tecnico', 'object_id': str(self.relatorio.pk), 'dirty_fields': [], 'fields': {'motivo': 'Nao deveria entrar'}}
        self.client.post(reverse('viagens_prestacoes:rt_autosave', args=[self.relatorio.pk]), data=json.dumps(payload), content_type='application/json')
        self.relatorio.refresh_from_db()
        self.assertEqual(self.relatorio.motivo, '')

    def test_payload_de_outro_modelo_e_recusado(self):
        response = self.client.post(reverse('viagens_prestacoes:rt_autosave', args=[self.relatorio.pk]), data=json.dumps({'model': 'prestacao_servidor', 'fields': {'motivo': 'X'}}), content_type='application/json')
        self.assertFalse(response.json()['ok'])
        self.relatorio.refresh_from_db()
        self.assertEqual(self.relatorio.motivo, '')
