"""`DB-06` — tirar um servidor da equipe do ofício não pode apagar o que ele entregou.

O sinal que reconcilia `PrestacaoServidor` com `oficio.servidores` fazia
`.delete()` em quem saía, e a cascata levava junto comprovante de saque e número
da solicitação. Trocar um servidor
no ofício é edição rotineira; destruir prova financeira já coletada não é.

Cada teste aqui existe para reprovar quando **uma** condição da correção cai.
Os que provam o oposto — que a linha sem nada continua sumindo — estão junto de
propósito: preservar tudo faria a prestação exibir servidores de outra equipe,
que é o defeito que o sinal foi escrito para resolver.
"""
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import reverse
from viagens_cadastros.models import Cargo
from viagens_cadastros.models import Servidor
from viagens_oficios.models import Oficio
from viagens_prestacoes.models import PrestacaoContas
from viagens_prestacoes.models import PrestacaoDocumentoAnexo
from viagens_prestacoes.models import PrestacaoServidor
from .test_helpers import autorizar_viagens, pdf_minimo
PDF_MINIMO = pdf_minimo()

class RemocaoDaEquipeBase(TestCase):

    def setUp(self):
        self.cargo = Cargo.objects.create(nome='Agente')
        self.servidor_a = Servidor.objects.create(nome='Servidor A', cargo=self.cargo, cpf='11122233344')
        self.servidor_b = Servidor.objects.create(nome='Servidor B', cargo=self.cargo, cpf='55566677788')
        for servidor in (self.servidor_a, self.servidor_b):
            servidor.refresh_from_db()
        self.oficio = Oficio.objects.create(numero=61, ano=2026, protocolo='606060606', status=Oficio.STATUS_RASCUNHO)
        self.oficio.servidores.add(self.servidor_a, self.servidor_b)
        self.prestacao = PrestacaoContas.objects.get(oficio=self.oficio)

    def _ps(self, servidor):
        return PrestacaoServidor.todos.get(prestacao=self.prestacao, servidor=servidor)

    def _anexar_comprovante(self, ps):
        return PrestacaoDocumentoAnexo.objects.create(prestacao=ps.prestacao, servidor_prestacao=ps, tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE, arquivo=SimpleUploadedFile('comprovante.pdf', PDF_MINIMO, content_type='application/pdf'), nome_original='comprovante.pdf')


class GateDB06Tests(RemocaoDaEquipeBase):
    """O gate literal de `docs/PLANO_BACKEND.md:100`.

    "teste que remove um servidor com anexo e exige que ele sobreviva" (a
    assinatura eletrônica, que também constava do gate, saiu do sistema).
    """

    def test_arquivo_do_comprovante_continua_no_disco(self):
        """A cascata deixava o arquivo órfão; aqui ele segue referenciado."""
        ps_a = self._ps(self.servidor_a)
        anexo = self._anexar_comprovante(ps_a)
        caminho = anexo.arquivo.name
        self.oficio.servidores.set([self.servidor_b])
        anexo.refresh_from_db()
        self.assertEqual(anexo.arquivo.name, caminho)
        self.assertTrue(anexo.arquivo.storage.exists(caminho))

    def test_remover_servidor_com_anexo_preserva_o_anexo(self):
        ps_a = self._ps(self.servidor_a)
        anexo = self._anexar_comprovante(ps_a)
        self.oficio.servidores.set([self.servidor_b])
        self.assertTrue(PrestacaoDocumentoAnexo.objects.filter(pk=anexo.pk).exists(), 'o comprovante de saque foi apagado pela troca de equipe')
        self.assertTrue(PrestacaoServidor.todos.filter(pk=ps_a.pk).exists(), 'a linha do servidor foi apagada, e com ela o vínculo dos anexos')

class RemocaoEscondeDaEquipeTests(RemocaoDaEquipeBase):
    """Preservar não é continuar exibindo: a equipe corrente exclui os removidos."""

    def test_servidor_removido_sai_da_equipe_corrente(self):
        ps_a = self._ps(self.servidor_a)
        self._anexar_comprovante(ps_a)
        self.oficio.servidores.set([self.servidor_b])
        self.assertEqual(set(self.prestacao.servidores_prestacao.values_list('servidor_id', flat=True)), {self.servidor_b.pk})

    def test_manager_padrao_esconde_e_todos_mostra(self):
        ps_a = self._ps(self.servidor_a)
        self._anexar_comprovante(ps_a)
        self.oficio.servidores.set([self.servidor_b])
        self.assertFalse(PrestacaoServidor.objects.filter(pk=ps_a.pk).exists())
        self.assertTrue(PrestacaoServidor.todos.filter(pk=ps_a.pk).exists())

    def test_prefetch_por_string_tambem_esconde(self):
        """`prefetch_related("servidores_prestacao")` não aceita filtro; herda o manager.

        É a razão de o filtro estar no `_default_manager` e não espalhado por
        quinze `filter(removida_em__isnull=True)` à mão: os `prefetch_related`
        por string de `view_common.py:257-262` não teriam onde recebê-lo.
        """
        ps_a = self._ps(self.servidor_a)
        self._anexar_comprovante(ps_a)
        self.oficio.servidores.set([self.servidor_b])
        prestacao = PrestacaoContas.objects.prefetch_related('servidores_prestacao').get(pk=self.prestacao.pk)
        self.assertEqual([ps.servidor_id for ps in prestacao.servidores_prestacao.all()], [self.servidor_b.pk])

    def test_default_manager_name_continua_no_manager_que_filtra(self):
        """Apontar `_default_manager` para `todos` desligaria tudo em silêncio.

        Nenhum teste de comportamento pegaria: as telas voltariam a listar os
        removidos e a suíte continuaria verde, porque quase toda leitura passa
        pelas relações reversas — que saem daqui.
        """
        self.assertEqual(PrestacaoServidor._meta.default_manager_name, 'objects')
        self.assertIs(PrestacaoServidor._default_manager.__class__, PrestacaoServidor.objects.__class__)

class LinhaSemDadosContinuaSendoApagadaTests(RemocaoDaEquipeBase):
    """O outro lado da regra, e ele importa tanto quanto o primeiro."""

    def test_servidor_sem_nada_coletado_e_apagado_de_fato(self):
        ps_a = self._ps(self.servidor_a)
        self.oficio.servidores.set([self.servidor_b])
        self.assertFalse(PrestacaoServidor.todos.filter(pk=ps_a.pk).exists())

class CadaSinalDeDadoColetadoPreservaTests(RemocaoDaEquipeBase):
    """Uma cláusula de `tem_dados_coletados()` por vez, e **só** ela.

    Cada caso aqui
    deixa exatamente um sinal ligado, de modo que remover a cláusula
    correspondente reprove este caso e nenhum outro.
    """

    def _oficio_novo(self, numero):
        """Ofício e prestação zerados, porque o estado **não** pode vir do caso anterior.

        Primeira versão reaproveitava um ofício só e reconstituía a equipe entre
        os casos — mas a linha preservada guardava o valor do caso anterior, então
        qualquer cláusula sozinha já bastava para preservar e sete das dez podiam
        ser apagadas do código sem nenhum teste reclamar.
        """
        oficio = Oficio.objects.create(numero=numero, ano=2026, protocolo=f'7{numero:08d}', status=Oficio.STATUS_RASCUNHO)
        oficio.servidores.add(self.servidor_a, self.servidor_b)
        prestacao = PrestacaoContas.objects.get(oficio=oficio)
        ps_a = PrestacaoServidor.todos.get(prestacao=prestacao, servidor=self.servidor_a)
        return (oficio, ps_a)

    def _assert_preservada(self, oficio, ps_a, mensagem):
        oficio.servidores.set([self.servidor_b])
        ps_a.refresh_from_db()
        self.assertIsNotNone(ps_a.removida_em, mensagem)

    def test_cada_campo_preenchido_pelo_usuario_preserva_a_linha(self):
        casos = [('numero_solicitacao', '2026/000123'), ('diaria_valor_override', Decimal('87.00')), ('diaria_valor_override_observacao', '(saque)'), ('data_liberacao_diarias', date(2026, 8, 3)), ('prazo_limite_saque', date(2026, 8, 10)), ('status', PrestacaoServidor.STATUS_ENVIADA), ('arquivada', True), ('finalizada', True)]
        for indice, (campo, valor) in enumerate(casos, start=1):
            with self.subTest(campo=campo):
                oficio, ps_a = self._oficio_novo(700 + indice)
                setattr(ps_a, campo, valor)
                ps_a.save(update_fields=[campo, 'atualizado_em'])
                self._assert_preservada(oficio, ps_a, f'`{campo}` preenchido não impediu a exclusão da linha')
                self.assertEqual(getattr(ps_a, campo), valor)

    def test_so_o_comprovante_ja_preserva(self):
        oficio, ps_a = self._oficio_novo(721)
        anexo = self._anexar_comprovante(ps_a)
        self._assert_preservada(oficio, ps_a, 'comprovante sozinho não preservou a linha')
        self.assertTrue(PrestacaoDocumentoAnexo.objects.filter(pk=anexo.pk).exists())


class VoltarParaEquipeRestauraTests(RemocaoDaEquipeBase):
    """O "desfazer" que o defeito dizia não existir."""

    def test_readicionar_servidor_traz_os_dados_de_volta(self):
        ps_a = self._ps(self.servidor_a)
        anexo = self._anexar_comprovante(ps_a)
        ps_a.numero_solicitacao = '2026/000123'
        ps_a.save(update_fields=['numero_solicitacao', 'atualizado_em'])
        self.oficio.servidores.set([self.servidor_b])
        self.oficio.servidores.add(self.servidor_a)
        restaurada = PrestacaoServidor.objects.get(prestacao=self.prestacao, servidor=self.servidor_a)
        self.assertEqual(restaurada.pk, ps_a.pk)
        self.assertIsNone(restaurada.removida_em)
        self.assertEqual(restaurada.numero_solicitacao, '2026/000123')
        self.assertEqual(list(restaurada.documentos_anexos.values_list('pk', flat=True)), [anexo.pk])

    def test_readicionar_nao_estoura_a_unicidade(self):
        """`get_or_create` pelo manager que filtra criaria uma segunda linha.

        E `unique_servidor_por_prestacao` transformaria a reedição de equipe em
        `IntegrityError` — erro 500 numa tela de uso diário.
        """
        ps_a = self._ps(self.servidor_a)
        self._anexar_comprovante(ps_a)
        self.oficio.servidores.set([self.servidor_b])
        self.oficio.servidores.add(self.servidor_a)
        self.assertEqual(PrestacaoServidor.todos.filter(prestacao=self.prestacao, servidor=self.servidor_a).count(), 1)

class BlocoDaTelaTests(RemocaoDaEquipeBase):
    """Preservar sem lugar de encontrar seria trocar um sumiço por outro."""

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(username='tester_db06', password='123456')
        self.client.force_login(self.user)
        autorizar_viagens(self.user)

    def _abrir_rt(self):
        ps_b = PrestacaoServidor.objects.get(prestacao=self.prestacao, servidor=self.servidor_b)
        return self.client.get(reverse('viagens_prestacoes:rt_servidor', args=[ps_b.pk]))

    def test_sem_ninguem_removido_o_bloco_nao_existe(self):
        """A metade que impede o bloco de virar ruído permanente na tela."""
        resposta = self._abrir_rt()
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'Saíram da equipe')

    def test_equipe_corrente_nao_lista_o_removido(self):
        """O mesmo request: o removido está no bloco novo e **não** no da equipe."""
        ps_a = self._ps(self.servidor_a)
        self._anexar_comprovante(ps_a)
        self.oficio.servidores.set([self.servidor_b])
        resposta = self._abrir_rt()
        corpo = resposta.content.decode()
        equipe, _, removidos = corpo.partition('prestacao-removidos-section')
        self.assertNotIn(self.servidor_a.nome, equipe)
        self.assertIn(self.servidor_a.nome, removidos)

    def test_servidor_removido_aparece_com_o_que_ficou_guardado(self):
        ps_a = self._ps(self.servidor_a)
        self._anexar_comprovante(ps_a)
        self.oficio.servidores.set([self.servidor_b])
        resposta = self._abrir_rt()
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Saíram da equipe')
        self.assertContains(resposta, self.servidor_a.nome)
        self.assertContains(resposta, 'comprovante')

class CamposConhecidosDoServidorDaPrestacaoTests(TestCase):
    """Congela os campos de `PrestacaoServidor` para forçar uma decisão consciente.

    `tem_dados_coletados()` decide se a linha é preservada ou apagada. Um campo
    novo que o usuário preencha e que não entre nessa conta volta a ser destruído
    pela troca de equipe — em silêncio, e sem nenhum teste vermelho. Quando este
    teste reprovar, a correção é decidir se o campo conta como dado coletado, e
    só então atualizar a lista.
    """
    # A marca histórica conta como dado coletado: a saída da equipe preserva a
    # linha importada e o rastro que permite conferir/reverter a migração.
    ESPERADOS = {'id', 'prestacao', 'servidor', 'numero_solicitacao', 'diaria_valor_override', 'diaria_valor_override_observacao', 'data_liberacao_diarias', 'prazo_limite_saque', 'status', 'arquivada', 'arquivada_em', 'finalizada', 'finalizada_em', 'removida_em', 'criado_em', 'atualizado_em', 'legado_origem', 'legado_pk'}

    def test_nenhum_campo_novo_escapou_de_tem_dados_coletados(self):
        atuais = {campo.name for campo in PrestacaoServidor._meta.concrete_fields}
        self.assertEqual(atuais, self.ESPERADOS)
