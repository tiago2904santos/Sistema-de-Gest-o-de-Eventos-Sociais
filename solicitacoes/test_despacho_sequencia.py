"""Despacho da DG em sequência: urgentes primeiro, próxima e textos prontos (m010)."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from cadastros.models import TextoDespacho

from .models import DecisaoDG, StatusSolicitacao
from .presenters import linha_da_lista
from .tests import BaseSolicitacaoTestCase


class BaseDespacho(BaseSolicitacaoTestCase):
    def setUp(self):
        self.hoje = timezone.localdate()

    def aguardando(self, dias, pedido_ha=30):
        inicio = self.hoje + timedelta(days=dias)
        solicitacao = self.criar_solicitacao(
            status=StatusSolicitacao.AGUARDANDO_DESPACHO,
            data_solicitacao=self.hoje - timedelta(days=pedido_ha),
            data_inicio_evento=inicio,
            data_fim_evento=inicio,
        )
        solicitacao.itens_servico.create(servico=self.servico)
        solicitacao.itens_equipe.create(equipe=self.equipe, quantidade_servidores=2)
        return solicitacao


class FilaDeDespachoTests(BaseDespacho):
    def test_evento_mais_proximo_primeiro(self):
        distante = self.aguardando(40)
        proxima = self.aguardando(2)
        media = self.aguardando(10)
        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("solicitacoes:lista"), {"fila": "despacho"})
        self.assertEqual(
            [linha["solicitacao"].pk for linha in resposta.context["linhas"]],
            [proxima.pk, media.pk, distante.pk],
        )

    def test_ordem_explicita_continua_valendo(self):
        self.aguardando(40)
        self.aguardando(2)
        self.client.force_login(self.gestor)
        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"fila": "despacho", "ordem": "-periodo"}
        )
        datas = [linha["solicitacao"].data_inicio_evento for linha in resposta.context["linhas"]]
        self.assertEqual(datas, sorted(datas, reverse=True))


class SeloDePrazoTests(BaseDespacho):
    def test_selo_vermelho_e_ambar(self):
        urgente = linha_da_lista(self.aguardando(2), {})
        self.assertEqual((urgente["quando"], urgente["quando_tom"]), ("Evento em 2 dias", "prazo_urgente"))
        proximo = linha_da_lista(self.aguardando(6), {})
        self.assertEqual(proximo["quando_tom"], "prazo_proximo")
        amanha = linha_da_lista(self.aguardando(1), {})
        self.assertEqual(amanha["quando"], "Evento amanhã")
        distante = linha_da_lista(self.aguardando(30), {})
        self.assertEqual(distante["quando"], "Previsto")

    def test_deferida_nao_ganha_selo_de_prazo(self):
        solicitacao = self.aguardando(2)
        solicitacao.status = StatusSolicitacao.DEFERIDA_EM_ANDAMENTO
        self.assertEqual(linha_da_lista(solicitacao, {})["quando"], "Previsto")

    def test_pedido_em_cima_da_hora(self):
        linha = linha_da_lista(self.aguardando(3, pedido_ha=1), {})
        alerta = [fato for fato in linha["fatos"] if fato.get("alerta")]
        self.assertEqual(len(alerta), 1)
        self.assertIn("4 dias antes", alerta[0]["texto"])
        com_folga = linha_da_lista(self.aguardando(30, pedido_ha=30), {})
        self.assertFalse([fato for fato in com_folga["fatos"] if fato.get("alerta")])


class ProximaDoDespachoTests(BaseDespacho):
    def test_contador_e_textos_na_tela(self):
        primeira = self.aguardando(2)
        self.aguardando(5)
        TextoDespacho.objects.create(nome="Falta ofício teste", texto="Anexe o ofício.")
        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[primeira.pk]))
        self.assertEqual(resposta.context["fila_despacho"], {"posicao": 1, "total": 2})
        self.assertContains(resposta, "1 de 2 na fila")
        self.assertContains(resposta, 'data-texto-pronto="Anexe o ofício."')
        self.assertContains(resposta, 'value="proxima"')

    def test_solicitante_nao_ve_o_despacho(self):
        primeira = self.aguardando(2)
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[primeira.pk]))
        self.assertNotIn("fila_despacho", resposta.context)

    def test_decidir_e_abrir_a_proxima(self):
        primeira = self.aguardando(2)
        segunda = self.aguardando(5)
        self.client.force_login(self.gestor)
        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[primeira.pk]),
            {"decisao": DecisaoDG.ATENDER, "observacao": "", "seguir": "proxima"},
        )
        self.assertRedirects(
            resposta,
            reverse("solicitacoes:editar", args=[segunda.pk]) + "#despacho-dg",
            fetch_redirect_response=False,
        )
        primeira.refresh_from_db()
        self.assertEqual(primeira.status, StatusSolicitacao.DEFERIDA_EM_ANDAMENTO)

    def test_ultima_da_fila_volta_para_a_lista(self):
        unica = self.aguardando(2)
        self.client.force_login(self.gestor)
        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[unica.pk]),
            {"decisao": "DEVOLVER", "observacao": "Ajuste o local.", "seguir": "proxima"},
        )
        self.assertRedirects(
            resposta,
            reverse("solicitacoes:lista") + "?fila=despacho",
            fetch_redirect_response=False,
        )


class TextosProntosNosCadastrosTests(BaseSolicitacaoTestCase):
    def test_dg_edita_textos_mas_nao_outros_cadastros(self):
        self.client.force_login(self.gestor)
        self.assertEqual(
            self.client.get(reverse("cadastros:lista", args=["textos-despacho"])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("cadastros:lista", args=["servicos"])).status_code, 403
        )
        resposta = self.client.post(
            reverse("cadastros:novo", args=["textos-despacho"]),
            {"nome": "Local indefinido", "texto": "Informe o local do evento."},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(TextoDespacho.objects.filter(nome="Local indefinido").exists())

    def test_solicitante_nao_edita_textos(self):
        self.client.force_login(self.solicitante)
        self.assertEqual(
            self.client.get(reverse("cadastros:lista", args=["textos-despacho"])).status_code,
            403,
        )
