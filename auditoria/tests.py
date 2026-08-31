from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from cadastros.models import Servico
from core.middleware import RequisicaoAtualMiddleware
from solicitacoes.models import AcaoHistorico, HistoricoSolicitacao, SolicitacaoEvento

from .models import RegistroAuditoria

User = get_user_model()


class RegistroAuditoriaSignalsTests(TestCase):
    def test_criacao_gera_registro_com_snapshot(self):
        with self.captureOnCommitCallbacks(execute=True):
            servico = Servico.objects.create(nome="Corte de cabelo")

        registro = RegistroAuditoria.objects.get(
            modelo="cadastros.servico", objeto_id=str(servico.pk)
        )
        self.assertEqual(registro.acao, RegistroAuditoria.Acao.CRIACAO)
        self.assertEqual(registro.alteracoes["novo"]["nome"], "Corte de cabelo")
        self.assertEqual(registro.objeto_repr, "Corte de cabelo")

    def test_atualizacao_gera_delta_apenas_dos_campos_alterados(self):
        servico = Servico.objects.create(nome="Corte de cabelo")
        with self.captureOnCommitCallbacks(execute=True):
            servico.nome = "Corte e barba"
            servico.save()

        registro = RegistroAuditoria.objects.get(
            acao=RegistroAuditoria.Acao.ATUALIZACAO, objeto_id=str(servico.pk)
        )
        self.assertEqual(
            registro.alteracoes["nome"],
            {"antes": "Corte de cabelo", "depois": "Corte e barba"},
        )
        self.assertNotIn("ativo", registro.alteracoes)
        # atualizado_em muda a cada save; os demais campos não aparecem.
        self.assertEqual(
            set(registro.alteracoes), {"nome", "atualizado_em"}
        )

    def test_exclusao_gera_registro_com_estado_antigo(self):
        servico = Servico.objects.create(nome="Fotografia")
        pk = servico.pk
        with self.captureOnCommitCallbacks(execute=True):
            servico.delete()

        registro = RegistroAuditoria.objects.get(
            acao=RegistroAuditoria.Acao.EXCLUSAO, objeto_id=str(pk)
        )
        self.assertEqual(registro.alteracoes["antigo"]["nome"], "Fotografia")

    def test_senha_nunca_entra_no_snapshot(self):
        # Sem senha de verdade: usuário de teste nunca autentica aqui e uma
        # dupla usuário/senha literal dispara o scanner de segredos do CI.
        with self.captureOnCommitCallbacks(execute=True):
            usuario = User.objects.create_user(username="fulana")

        registro = RegistroAuditoria.objects.get(
            modelo="accounts.user", objeto_id=str(usuario.pk)
        )
        self.assertNotIn("password", registro.alteracoes["novo"])
        self.assertEqual(registro.alteracoes["novo"]["username"], "fulana")

    def test_transacao_abortada_nao_deixa_rastro(self):
        # Sem commit, o on_commit não executa: nada é gravado.
        Servico.objects.create(nome="Efêmero")
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_historico_de_solicitacao_fica_fora_da_trilha(self):
        criador = User.objects.create_user(username="criadora")
        solicitacao = SolicitacaoEvento.objects.create(criado_por=criador)
        with self.captureOnCommitCallbacks(execute=True):
            HistoricoSolicitacao.objects.create(
                solicitacao=solicitacao,
                acao=AcaoHistorico.CRIACAO,
                status_novo=solicitacao.status,
            )
        self.assertFalse(
            RegistroAuditoria.objects.filter(
                modelo="solicitacoes.historicosolicitacao"
            ).exists()
        )

    def test_usuario_e_caminho_vem_da_requisicao_corrente(self):
        usuario = User.objects.create_user(username="agente")
        requisicao = RequestFactory().post("/cadastros/servicos/novo/")
        requisicao.user = usuario

        def view(request):
            Servico.objects.create(nome="Locução")
            return HttpResponse()

        with self.captureOnCommitCallbacks(execute=True):
            RequisicaoAtualMiddleware(view)(requisicao)

        registro = RegistroAuditoria.objects.get(modelo="cadastros.servico")
        self.assertEqual(registro.usuario, usuario)
        self.assertEqual(registro.caminho_requisicao, "/cadastros/servicos/novo/")


class RegistroAuditoriaImutabilidadeTests(TestCase):
    def _registro(self):
        return RegistroAuditoria.objects.create(
            acao=RegistroAuditoria.Acao.CRIACAO,
            modelo="cadastros.servico",
            objeto_id="1",
        )

    def test_update_e_recusado(self):
        registro = self._registro()
        registro.objeto_repr = "adulterado"
        with self.assertRaises(TypeError):
            registro.save()

    def test_delete_e_recusado(self):
        registro = self._registro()
        with self.assertRaises(TypeError):
            registro.delete()
