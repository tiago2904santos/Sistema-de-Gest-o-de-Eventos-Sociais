"""`BE-14` fatia 1 — rede para a gravação do relatório técnico, antes de ela sair da view.

O `BE-14` fala em "envolver em transação", e aqui a leitura ingênua **está errada**. O
código já explica por quê, em `rt_views.py:271-274`:

    # O texto do RT já foi salvo acima; o que não entrou foi só o valor
    # recusado. Salvar automaticamente um valor que a regra proíbe seria
    # pior que devolver erro: ninguém revisa o que salvou sozinho.

Ou seja: uma diária **recusada pela regra** não pode desfazer o texto que o operador acabou
de digitar. Isso é decisão de desenho, e a transação não pode revogá-la — `erros` é valor de
retorno, não exceção, então um `atomic` em volta commita normalmente. O cenário 2 existe para
provar isso em vez de confiar.

O defeito de verdade é mais estreito: `_salvar_diaria_overrides` percorre N servidores e grava
um `UPDATE` por servidor. Se o terceiro falhar de verdade, os dois primeiros já foram
gravados — e é dinheiro por servidor. É o cenário 4, o único que reprova hoje.

Os cenários 1 e 3 fecham uma lacuna medida antes de escrever: `rt_servidor_autosave`
(`rt_views.py:201`) **não era exercido por nenhum teste do repositório**, e ele difere de
`rt_autosave` só na marcação de status. Sem eles, mover as duas para um service com um
parâmetro de escopo apagaria a divergência sem ninguém notar.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
import json
from decimal import Decimal
from unittest import mock
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes.models import PrestacaoServidor
from viagens_prestacoes.models import RelatorioTecnico
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin

class RelatorioTecnicoTransacaoTests(PrestacaoFixturesMixin, TestCase):
    """O que as duas rotas de autosave do RT gravam, e o que sobra quando falha."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.segundo = self.criar_servidor('Segundo Servidor RT')
        self.fixture = self.criar_prestacao(numero=41, servidores=[self.criar_servidor('Primeiro Servidor RT'), self.segundo])
        self.prestacao = self.fixture.prestacao
        self.ps_a, self.ps_b = self.fixture.prestacoes_servidor
        self.relatorio = RelatorioTecnico.objects.create(prestacao=self.prestacao)

    def _payload(self, campos):
        return json.dumps({'model': 'relatorio_tecnico', 'object_id': str(self.relatorio.pk), 'dirty_fields': list(campos), 'fields': campos})

    def autosave_por_servidor(self, **campos):
        """`rt_servidor_autosave` — a rota que não tinha teste nenhum."""
        return self.client.post(reverse('viagens_prestacoes:rt_servidor_autosave', args=[self.ps_a.pk]), data=self._payload(campos), content_type='application/json')

    def autosave_por_relatorio(self, **campos):
        """`rt_autosave` — a rota antiga, por pk do relatório."""
        return self.client.post(reverse('viagens_prestacoes:rt_autosave', args=[self.relatorio.pk]), data=self._payload(campos), content_type='application/json')

    def test_autosave_por_servidor_grava_texto_do_rt_e_valor_da_diaria(self):
        """Cenário 1: a rota descoberta grava as duas coisas numa requisição só."""
        resposta = self.autosave_por_servidor(**{'motivo': 'Fiscalização de rotina', f'ps-{self.ps_a.pk}-diaria_valor_override': 'R$ 120,00'})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(json.loads(resposta.content)['ok'])
        self.relatorio.refresh_from_db()
        self.ps_a.refresh_from_db()
        self.assertEqual(self.relatorio.motivo, 'Fiscalização de rotina')
        self.assertEqual(self.ps_a.diaria_valor_override, Decimal('120.00'))

    def test_diaria_recusada_nao_desfaz_o_texto_do_rt_ja_salvo(self):
        """Cenário 2: a decisão de desenho que a transação **não** pode revogar.

        `rt_views.py:271-274` diz em prosa que o texto do RT fica salvo mesmo quando o
        valor da diária é recusado. Se um dia alguém envolver o par numa transação que
        desfaça tudo, este teste reprova — que é exatamente o ponto.
        """
        resposta = self.autosave_por_relatorio(**{'conclusao': 'Atividade concluída sem intercorrências', f'ps-{self.ps_a.pk}-diaria_valor_override': 'não é dinheiro'})
        corpo = json.loads(resposta.content)
        self.assertFalse(corpo['ok'], 'o valor inválido tinha de ser recusado')
        self.assertIn(f'ps-{self.ps_a.pk}-diaria_valor_override', corpo['errors'])
        self.relatorio.refresh_from_db()
        self.ps_a.refresh_from_db()
        self.assertEqual(self.relatorio.conclusao, 'Atividade concluída sem intercorrências', 'o texto do RT não pode voltar atrás por causa da diária recusada')
        self.assertIsNone(self.ps_a.diaria_valor_override, 'o valor recusado não entra')

    def test_as_duas_rotas_marcam_status_diferente(self):
        """Cenário 3: a única divergência entre os dois autosaves, travada.

        `rt_servidor_autosave` marca **só o servidor da URL**; `rt_autosave` marca
        **toda a equipe pendente**. Extrair as duas para um service com parâmetro de
        escopo só é seguro se essa diferença estiver fotografada.
        """
        self.autosave_por_servidor(motivo='Só o servidor da URL')
        self.ps_a.refresh_from_db()
        self.ps_b.refresh_from_db()
        self.assertEqual(self.ps_a.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO)
        self.assertEqual(self.ps_b.status, PrestacaoServidor.STATUS_PENDENTE, 'a rota por servidor não pode marcar o colega')
        self.autosave_por_relatorio(atividade='Agora a equipe toda')
        self.ps_b.refresh_from_db()
        self.assertEqual(self.ps_b.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO, 'a rota por relatório marca todos os pendentes')

    def test_falha_no_meio_do_laco_nao_deixa_meia_gravacao_de_diaria(self):
        """Cenário 4: era o defeito, e é a razão de `salvar_diarias_recebidas` ser atômica.

        Reprovava no commit da rede (`Decimal('100.00') is not None`) e passou a valer
        quando o laço saiu da view para o service com `@transaction.atomic`.

        Dois servidores no mesmo POST, e o `save` do segundo falha. Sem transação, o
        primeiro já está gravado no banco e o operador vê um valor pela metade — em
        dinheiro, por servidor, sem nada na tela dizendo que faltou o outro.
        """
        original = PrestacaoServidor.save
        chamadas = []

        def falhar_na_segunda(self_ps, *args, **kwargs):
            chamadas.append(self_ps.pk)
            if len(chamadas) == 2:
                raise RuntimeError('falha no meio do laço de diárias')
            return original(self_ps, *args, **kwargs)
        with mock.patch.object(PrestacaoServidor, 'save', falhar_na_segunda):
            with self.assertRaises(RuntimeError):
                self.autosave_por_relatorio(**{f'ps-{self.ps_a.pk}-diaria_valor_override': 'R$ 100,00', f'ps-{self.ps_b.pk}-diaria_valor_override': 'R$ 200,00'})
        self.ps_a.refresh_from_db()
        self.ps_b.refresh_from_db()
        self.assertIsNone(self.ps_a.diaria_valor_override, 'sobrou meia gravação: o primeiro servidor ficou com valor e o segundo não')
        self.assertIsNone(self.ps_b.diaria_valor_override)

class AutosaveDoRtEUmaOperacaoSoTests(PrestacaoFixturesMixin, TestCase):
    """Por que `salvar_rt_do_autosave` também é `@transaction.atomic`.

    O decorador de dentro (`salvar_diarias_recebidas`) já segura o laço; este segura o
    **conjunto** — texto do RT, diárias e marcação de status são uma operação só. Sem
    ele, uma falha na marcação deixaria o texto gravado e o servidor ainda "pendente",
    e é a marcação que faz a prestação aparecer como iniciada na lista.

    Sem este teste o decorador de fora seria enfeite: nenhuma inversão o alcançaria.
    """

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=44)
        self.ps = self.fixture.prestacoes_servidor[0]
        self.relatorio = RelatorioTecnico.objects.create(prestacao=self.fixture.prestacao)

    def test_falha_ao_marcar_status_desfaz_o_texto_do_rt(self):
        from viagens_prestacoes import rt_services

        def explodir(_servidor_prestacao):
            raise RuntimeError('falha ao marcar o status')
        with mock.patch.object(rt_services, 'marcar_servidor_em_preenchimento', explodir):
            with self.assertRaises(RuntimeError):
                rt_services.salvar_rt_do_autosave(self.relatorio, self.fixture.prestacao, fields={'motivo': 'Não pode sobrar'}, dirty_fields=['motivo'], escopo=rt_services.ESCOPO_SERVIDOR, servidor_prestacao=self.ps)
        self.relatorio.refresh_from_db()
        self.assertEqual(self.relatorio.motivo, '', 'o texto ficou gravado com o status não marcado: não é uma operação só')

class DiariasRecebidasAtomicaSozinhaTests(PrestacaoFixturesMixin, TestCase):
    """`salvar_diarias_recebidas` protege o laço **sozinha**, sem depender do chamador.

    Existe porque a primeira inversão não provou o que eu achava que provava: tirar o
    `@transaction.atomic` de `salvar_diarias_recebidas` **não** reprovava o cenário 4,
    porque `salvar_rt_do_autosave` também é atômica e o decorador de fora segurava a
    garantia — `atomic` aninhado vira SAVEPOINT, e o rollback acontecia de qualquer
    jeito.

    Isso deixaria a função pública sem rede própria: um chamador futuro que entrasse
    direto — como o `BE-12` fez com `salvar_roteiro_do_oficio` — herdaria a meia
    gravação de volta. Aqui ela é chamada sem invólucro nenhum, que é o cenário desse
    chamador.
    """

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=43, servidores=[self.criar_servidor('Alfa'), self.criar_servidor('Beta')])
        self.ps_a, self.ps_b = self.fixture.prestacoes_servidor

    def test_chamada_direta_nao_deixa_meia_gravacao(self):
        from viagens_prestacoes.rt_services import salvar_diarias_recebidas
        original = PrestacaoServidor.save
        chamadas = []

        def falhar_na_segunda(self_ps, *args, **kwargs):
            chamadas.append(self_ps.pk)
            if len(chamadas) == 2:
                raise RuntimeError('falha no meio do laço, sem invólucro')
            return original(self_ps, *args, **kwargs)
        with mock.patch.object(PrestacaoServidor, 'save', falhar_na_segunda):
            with self.assertRaises(RuntimeError):
                salvar_diarias_recebidas(self.fixture.prestacao, {f'ps-{self.ps_a.pk}-diaria_valor_override': 'R$ 100,00', f'ps-{self.ps_b.pk}-diaria_valor_override': 'R$ 200,00'})
        self.ps_a.refresh_from_db()
        self.assertIsNone(self.ps_a.diaria_valor_override, 'sem invólucro atômico por fora, a própria função tem de segurar o laço')

class MarcarServidoresPendentesTests(PrestacaoFixturesMixin, TestCase):
    """Por que `services.marcar_servidores_pendentes` virou `@transaction.atomic`.

    Ela grava em laço, um `UPDATE` por servidor pendente, e nenhum dos chamadores abre
    transação — são as views de RT, diário e documentos. A metade que sobra **não se
    conserta na gravação seguinte**: quem já saiu de "pendente" deixa de entrar no
    filtro, então o laço nem tenta de novo.
    """

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=42, servidores=[self.criar_servidor('Um'), self.criar_servidor('Dois'), self.criar_servidor('Tres')])

    def test_falha_no_meio_do_laco_nao_marca_ninguem(self):
        from viagens_prestacoes.services import marcar_servidores_pendentes
        original = PrestacaoServidor.save
        chamadas = []

        def falhar_na_segunda(self_ps, *args, **kwargs):
            chamadas.append(self_ps.pk)
            if len(chamadas) == 2:
                raise RuntimeError('falha no meio do laço de marcação')
            return original(self_ps, *args, **kwargs)
        with mock.patch.object(PrestacaoServidor, 'save', falhar_na_segunda):
            with self.assertRaises(RuntimeError):
                marcar_servidores_pendentes(self.fixture.prestacao)
        status = list(self.fixture.prestacao.servidores_prestacao.order_by('pk').values_list('status', flat=True))
        self.assertEqual(status, [PrestacaoServidor.STATUS_PENDENTE] * 3, "sobrou marcação pela metade, e o laço não a reencontra: quem saiu de 'pendente' não volta ao filtro")
