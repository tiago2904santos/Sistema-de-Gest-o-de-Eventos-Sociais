"""Sugestões da tela da solicitação, aplicadas com um clique (m008, m009)."""

from django.urls import reverse

from cadastros.models import Equipe, OrgaoResponsavel, Servico, TipoEvento, TipoEventoEquipe

from .models import StatusSolicitacao
from .sugestoes import sugestao_do_tipo
from .tests import BaseSolicitacaoTestCase


class SugestaoDoTipoTests(BaseSolicitacaoTestCase):
    def test_modelo_do_tipo(self):
        tipo = TipoEvento.objects.create(
            nome="Feira de saúde",
            solicitante_padrao="Secretaria de Saúde",
            cargo_padrao="Coordenação",
            orgao_padrao=self.orgao,
        )
        tipo.servicos_sugeridos.add(self.servico)
        TipoEventoEquipe.objects.create(tipo_evento=tipo, equipe=self.equipe, quantidade=4)

        sugestao = sugestao_do_tipo(tipo.pk)

        self.assertEqual(sugestao["tipo"], "Feira de saúde")
        self.assertEqual(sugestao["origem"], ["o modelo do tipo"])
        self.assertEqual(sugestao["servicos"], [{"id": self.servico.pk, "nome": "Emissão de CIN"}])
        self.assertEqual(
            sugestao["equipes"], [{"id": self.equipe.pk, "nome": "Equipe Alfa", "quantidade": 4}]
        )
        self.assertEqual(
            sugestao["solicitante"],
            {
                "nome": "Secretaria de Saúde",
                "cargo": "Coordenação",
                "orgao": {"id": self.orgao.pk, "nome": "Órgão Teste"},
            },
        )

    def test_sem_modelo_usa_o_historico_do_tipo(self):
        for quantidade in (5, 5, 3):
            solicitacao = self.criar_solicitacao(status=StatusSolicitacao.AGUARDANDO_DESPACHO)
            solicitacao.itens_servico.create(servico=self.servico)
            solicitacao.itens_equipe.create(equipe=self.equipe, quantidade_servidores=quantidade)
        rara = self.criar_solicitacao(status=StatusSolicitacao.ATENDIDA)
        rara.itens_servico.create(servico=self.outro_servico)
        # Rascunho não conta.
        self.criar_solicitacao().itens_servico.create(servico=self.outro_servico)

        sugestao = sugestao_do_tipo(self.tipo.pk)

        self.assertEqual(sugestao["origem"], ["as últimas 4 solicitações deste tipo"])
        self.assertEqual([s["id"] for s in sugestao["servicos"]], [self.servico.pk])
        self.assertEqual(sugestao["equipes"][0]["quantidade"], 5)
        self.assertIsNone(sugestao["solicitante"])

    def test_parana_em_acao_ja_vem_com_o_solicitante_no_modelo(self):
        # A migração transformou a regra fixa no modelo do tipo.
        tipo = TipoEvento.objects.get(nome="Paraná em Ação")
        sugestao = sugestao_do_tipo(tipo.pk)
        self.assertEqual(sugestao["solicitante"]["nome"], "Paraná em Ação")
        self.assertEqual(sugestao["solicitante"]["cargo"], "SEJU")

    def test_inativos_ficam_de_fora(self):
        inativo = Servico.objects.create(nome="Serviço antigo", ativo=False)
        equipe_inativa = Equipe.objects.create(nome="Equipe antiga", ativo=False)
        tipo = TipoEvento.objects.create(nome="Outro tipo")
        tipo.servicos_sugeridos.add(inativo, self.servico)
        TipoEventoEquipe.objects.create(tipo_evento=tipo, equipe=equipe_inativa)
        sugestao = sugestao_do_tipo(tipo.pk)
        self.assertEqual([s["id"] for s in sugestao["servicos"]], [self.servico.pk])
        self.assertEqual(sugestao["equipes"], [])

    def test_endpoint_json(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:sugestao_tipo"), {"tipo": self.tipo.pk})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["tipo"], "Ação social")
        vazio = self.client.get(reverse("solicitacoes:sugestao_tipo"), {"tipo": "x"}).json()
        self.assertEqual(vazio["servicos"], [])

    def test_tela_tem_a_caixa_de_sugestao_so_quando_editavel(self):
        self.client.force_login(self.solicitante)
        self.assertContains(self.client.get(reverse("solicitacoes:nova")), "data-sugestao-tipo")
        enviada = self.criar_solicitacao(status=StatusSolicitacao.AGUARDANDO_DESPACHO)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[enviada.pk]))
        self.assertNotContains(resposta, "data-sugestao-tipo")


class ModeloDoTipoNosCadastrosTests(BaseSolicitacaoTestCase):
    def test_administrador_salva_o_modelo(self):
        outro_orgao = OrgaoResponsavel.objects.create(nome="SEJU")
        self.client.force_login(self.administrador)
        url = reverse("cadastros:modelo_tipo_evento", args=[self.tipo.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

        resposta = self.client.post(
            url,
            {
                "solicitante_padrao": "Programa X",
                "cargo_padrao": "SEJU",
                "orgao_padrao": outro_orgao.pk,
                "servicos_sugeridos": [self.servico.pk, self.outro_servico.pk],
                "equipes": [self.equipe.pk],
                f"quantidade_{self.equipe.pk}": "6",
                f"quantidade_{self.outra_equipe.pk}": "9",  # não marcada: ignora
            },
        )

        self.assertRedirects(resposta, reverse("cadastros:lista", args=["tipos-evento"]), fetch_redirect_response=False)
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.solicitante_padrao, "Programa X")
        self.assertEqual(self.tipo.orgao_padrao, outro_orgao)
        self.assertEqual(self.tipo.servicos_sugeridos.count(), 2)
        self.assertEqual(
            list(self.tipo.equipes_sugeridas.values_list("equipe_id", "quantidade")),
            [(self.equipe.pk, 6)],
        )

    def test_quantidade_invalida_nao_salva(self):
        self.client.force_login(self.administrador)
        url = reverse("cadastros:modelo_tipo_evento", args=[self.tipo.pk])
        resposta = self.client.post(
            url, {"equipes": [self.equipe.pk], f"quantidade_{self.equipe.pk}": "0"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Informe uma quantidade válida")
        self.assertFalse(self.tipo.equipes_sugeridas.exists())

    def test_solicitante_nao_edita_o_modelo(self):
        self.client.force_login(self.solicitante)
        url = reverse("cadastros:modelo_tipo_evento", args=[self.tipo.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_link_no_menu_do_tipo(self):
        self.client.force_login(self.administrador)
        resposta = self.client.get(reverse("cadastros:lista", args=["tipos-evento"]))
        self.assertContains(resposta, reverse("cadastros:modelo_tipo_evento", args=[self.tipo.pk]))
