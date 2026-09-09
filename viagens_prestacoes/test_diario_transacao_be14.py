"""`BE-14` fatia 4 — rede para a gravação do diário de bordo, a última do defeito.

Três caminhos de escrita em `diario_views.py`, nenhum em transação:

1. **O autosave**, que grava `linha.save(...)` dentro de um laço e depois `diario.save()`.
   Duas linhas sujas são duas gravações; uma falha entre elas deixa metade.
   (Quando esta fatia foi escrita o laço era **por campo sujo**, e o teste da falha
   injetava na segunda gravação da *mesma* linha. O `NOVO-116` juntou os campos de uma
   linha numa gravação só — o estado intermediário violava o `diario_trecho_km_ordenado`
   —, então o ponto de injeção passou a ser a **segunda linha**. A garantia é a mesma.)
2. **A troca de motorista/viatura**, que grava três vezes: o form do diário, a prévia de
   "informações complementares" do RT, e a marcação de status. Uma falha no meio deixa o
   motorista trocado com o texto do RT desatualizado — e é justamente o texto que explica
   a troca no documento.
3. **O POST do formset**, que grava N linhas de km e abastecimento de uma vez.

`sincronizar_trechos` já é `@transaction.atomic` desde o `DB-08` fatia 2, e é chamada
antes destes três. Ou seja: a parte que **cria** as linhas do diário é atômica, e a parte
que **preenche** não era.

Como nas fatias 1 e 3, as duas rotas de autosave divergem na marcação de status —
`diario_servidor_autosave` marca só o servidor da URL, `diario_autosave` marca a equipe
pendente inteira. E como na fatia 1, a rota por servidor **não tinha teste nenhum**.

`NOVO-107` fechou a armadilha da fixture: `criar_prestacao` agora monta roteiro por
padrão. Testes que exercitam laços informam `trechos_roteiro=N` na própria criação.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
import json
from unittest import mock
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_prestacoes.models import DiarioBordo
from viagens_prestacoes.models import DiarioBordoTrecho
from viagens_prestacoes.models import PrestacaoServidor
from viagens_prestacoes.models import RelatorioTecnico
from viagens_prestacoes.test_helpers import PrestacaoFixturesMixin

class DiarioAutosaveTests(PrestacaoFixturesMixin, TestCase):
    """O autosave do diário, pelas duas rotas."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=71, servidores=[self.criar_servidor('Um DB'), self.criar_servidor('Dois DB')], trechos_roteiro=2)
        self.prestacao = self.fixture.prestacao
        self.ps_a, self.ps_b = self.fixture.prestacoes_servidor
        self.diario, _ = DiarioBordo.objects.get_or_create(prestacao=self.prestacao)

    def _payload(self, campos):
        return json.dumps({'model': 'diario_bordo', 'object_id': str(self.diario.pk), 'dirty_fields': list(campos), 'fields': campos})

    def autosave_por_servidor(self, **campos):
        """`diario_servidor_autosave` — a rota que não tinha teste nenhum."""
        return self.client.post(reverse('viagens_prestacoes:diario_servidor_autosave', args=[self.ps_a.pk]), data=self._payload(campos), content_type='application/json')

    def autosave_por_diario(self, **campos):
        return self.client.post(reverse('viagens_prestacoes:diario_autosave', args=[self.diario.pk]), data=self._payload(campos), content_type='application/json')

    def _linhas(self):
        return list(self.diario.trechos.order_by('ordem', 'pk'))

    def test_a_fixture_produz_linha_de_diario(self):
        """Guarda contra o cenário vazio: sem linha, os testes abaixo não medem nada."""
        self.client.get(reverse('viagens_prestacoes:diario_servidor', args=[self.ps_a.pk]))
        self.assertTrue(self._linhas(), 'sem linha de diário a rede seria verde por omissão')

    def test_autosave_por_servidor_grava_km_e_abastecimento(self):
        resposta = self.autosave_por_servidor(**{'form-0-km_inicial': '1.200', 'form-0-abastecimento': 'sim'})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(json.loads(resposta.content)['ok'])
        linha = self._linhas()[0]
        self.assertEqual(linha.km_inicial, 1200)
        self.assertTrue(linha.abastecimento)

    def test_as_duas_rotas_marcam_status_diferente(self):
        """A mesma divergência de escopo das fatias 1 e 3, travada antes de extrair."""
        self.autosave_por_servidor(**{'form-0-km_inicial': '10'})
        self.ps_a.refresh_from_db()
        self.ps_b.refresh_from_db()
        self.assertEqual(self.ps_a.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO)
        self.assertEqual(self.ps_b.status, PrestacaoServidor.STATUS_PENDENTE, 'a rota por servidor não pode marcar o colega')
        self.autosave_por_diario(**{'form-0-km_final': '20'})
        self.ps_b.refresh_from_db()
        self.assertEqual(self.ps_b.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO, 'a rota por diário marca todos os pendentes')

    def test_falha_no_meio_do_laco_nao_deixa_meia_gravacao(self):
        """O defeito, e a garantia que esta fatia entrega.

        Duas linhas sujas, e a gravação da segunda falha. Sem transação, a primeira já
        está no banco — o operador vê uma linha salva e a outra não, sem nada dizendo
        que faltou.

        Reprovava no commit da rede; passou a valer quando o laço foi para dentro de
        `salvar_autosave_do_diario`, que é `@transaction.atomic`.

        O ponto de injeção era a segunda gravação da *mesma* linha, quando o laço ainda
        era por campo sujo. O `NOVO-116` juntou os campos de uma linha numa gravação só,
        então passou a ser a segunda **linha** — mesma garantia, mesma rede.
        """
        self.client.get(reverse("viagens_prestacoes:diario_servidor", args=[self.ps_a.pk]))
        original = DiarioBordoTrecho.save
        chamadas = []
        CAMPOS_DO_AUTOSAVE = {'km_inicial', 'km_final', 'abastecimento'}

        def falhar_na_segunda(self_linha, *args, **kwargs):
            if set(kwargs.get('update_fields') or ()) & CAMPOS_DO_AUTOSAVE:
                chamadas.append(self_linha.pk)
                if len(chamadas) == 2:
                    raise RuntimeError('falha no meio do laço do diário')
            return original(self_linha, *args, **kwargs)
        with mock.patch.object(DiarioBordoTrecho, 'save', falhar_na_segunda):
            with self.assertRaises(RuntimeError):
                self.autosave_por_diario(**{'form-0-km_inicial': '500', 'form-1-km_inicial': '700'})
        self.assertEqual(len(chamadas), 2, 'o laço não chegou à segunda linha')
        linha = self._linhas()[0]
        self.assertIsNone(linha.km_inicial, 'sobrou meia gravação: a primeira linha entrou e a segunda não')

class FormsetDoDiarioTests(PrestacaoFixturesMixin, TestCase):
    """O `POST` do formset: N linhas de uma vez, e a marcação de status como N+1.

    É o caminho sem JS — o que o operador usa quando aperta "gerar" com os campos
    preenchidos na mão. Grava tantas linhas quantos forem os trechos do roteiro.
    """

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=73, trechos_roteiro=2)
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        self.diario, _ = DiarioBordo.objects.get_or_create(prestacao=self.prestacao)
        self.client.get(reverse('viagens_prestacoes:diario_servidor', args=[self.ps.pk]))
        self.linhas = list(self.diario.trechos.order_by('ordem', 'pk'))
        self.assertEqual(len(self.linhas), 2, 'sem duas linhas o teste não mede o laço')

    def postar(self):
        dados = {'form-TOTAL_FORMS': str(len(self.linhas)), 'form-INITIAL_FORMS': str(len(self.linhas)), 'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000'}
        for i, linha in enumerate(self.linhas):
            dados[f'form-{i}-id'] = str(linha.pk)
            dados[f'form-{i}-km_inicial'] = str(100 + i)
            dados[f'form-{i}-km_final'] = str(200 + i)
            dados[f'form-{i}-abastecimento'] = 'sim'
        return self.client.post(reverse('viagens_prestacoes:diario_servidor', args=[self.ps.pk]), dados)

    def test_post_grava_as_linhas_e_marca_o_servidor(self):
        resposta = self.postar()
        self.assertEqual(resposta.status_code, 302)
        for i, linha in enumerate(self.linhas):
            linha.refresh_from_db()
            self.assertEqual(linha.km_inicial, 100 + i)
            self.assertEqual(linha.km_final, 200 + i)
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO)

    def test_falha_ao_marcar_o_status_nao_deixa_as_linhas_gravadas(self):
        """A garantia da terceira transação desta fatia.

        A falha entra na marcação, que é a gravação **seguinte** ao `formset.save()`.
        Sem transação, o usuário leva 500 — para ele o "gerar" não aconteceu — mas os
        km já estão no banco e o servidor continua "pendente", um par que a tela nunca
        mostra junto.

        Como na fatia 3, o ponto de injeção é `PrestacaoServidor.save` e não um nome de
        módulo: a marcação já mudou de arquivo uma vez neste defeito.
        """

        def falhar(*args, **kwargs):
            raise RuntimeError('falha ao marcar o status depois de gravar as linhas')
        with mock.patch.object(PrestacaoServidor, 'save', falhar):
            with self.assertRaises(RuntimeError):
                self.postar()
        linha = self.linhas[0]
        linha.refresh_from_db()
        self.assertIsNone(linha.km_inicial, 'as linhas ficaram gravadas numa operação que falhou e não deu resposta')

class TrocaDeMotoristaTests(PrestacaoFixturesMixin, TestCase):
    """A troca de motorista/viatura grava três vezes, e nenhuma em transação."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.outro = self.criar_servidor('Condutor Novo')
        self.fixture = self.criar_prestacao(numero=72, servidores=[self.criar_servidor('Titular DB'), self.outro])
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        self.diario, _ = DiarioBordo.objects.get_or_create(prestacao=self.prestacao)
        self.relatorio = RelatorioTecnico.objects.create(prestacao=self.prestacao)

    def url(self):
        return reverse('viagens_prestacoes:diario_servidor_motorista', args=[self.ps.pk])

    def trocar(self, **campos):
        dados = {'motorista_modo': DiarioBordo.MOTORISTA_MODO_SERVIDOR, 'motorista_servidor': self.outro.pk, 'viatura_modo': self.diario.viatura_modo or 'OFICIO'}
        dados.update(campos)
        return self.client.post(self.url(), dados)

    def test_troca_grava_o_diario_e_marca_o_servidor(self):
        resposta = self.trocar()
        self.assertEqual(resposta.status_code, 302)
        self.diario.refresh_from_db()
        self.ps.refresh_from_db()
        self.assertEqual(self.diario.motorista_modo, DiarioBordo.MOTORISTA_MODO_SERVIDOR)
        self.assertEqual(self.diario.motorista_servidor_id, self.outro.pk)
        self.assertEqual(self.ps.status, PrestacaoServidor.STATUS_EM_PREENCHIMENTO)

    def test_falha_ao_sincronizar_o_rt_nao_deixa_o_motorista_trocado_sozinho(self):
        """O segundo defeito, e a garantia que esta fatia entrega.

        A troca grava o diário, depois gera a prévia de "informações complementares" do
        RT — que é o texto que **explica a troca** no documento — e depois marca o
        status. Se a segunda falhar, o motorista fica trocado e o documento sai sem a
        explicação, sem nada na tela dizendo isso.

        Reprovava no commit da rede; passou a valer quando as três gravações foram para
        dentro de `trocar_motorista_do_diario`, que é `@transaction.atomic`.
        """

        def falhar(*args, **kwargs):
            raise RuntimeError('falha ao sincronizar o RT depois da troca')
        with mock.patch.object(RelatorioTecnico, 'save', falhar):
            with self.assertRaises(RuntimeError):
                self.trocar()
        self.diario.refresh_from_db()
        self.assertNotEqual(self.diario.motorista_modo, DiarioBordo.MOTORISTA_MODO_SERVIDOR, 'o motorista ficou trocado com o RT não sincronizado')
