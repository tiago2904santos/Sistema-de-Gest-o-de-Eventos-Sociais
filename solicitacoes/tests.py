from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from cadastros.models import (
    Equipe,
    Motorista,
    Municipio,
    OrgaoResponsavel,
    Regiao,
    Servico,
    TipoEvento,
)

from .forms import DespachoForm, SolicitacaoForm
from .models import (
    AcaoHistorico,
    DecisaoDG,
    SolicitacaoEvento,
    StatusSolicitacao,
)
from .permissions import GRUPO_ANALISTA, GRUPO_GESTOR_DG
from . import services

User = get_user_model()


class BaseSolicitacaoTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.regiao = Regiao.objects.create(nome="Região Teste")
        cls.outra_regiao = Regiao.objects.create(nome="Outra Região")
        cls.municipio = Municipio.objects.create(nome="Cidade Teste", regiao=cls.regiao)
        cls.tipo = TipoEvento.objects.create(nome="Ação social")
        cls.orgao = OrgaoResponsavel.objects.create(nome="Órgão Teste")
        cls.servico = Servico.objects.create(nome="Emissão de CIN")
        cls.outro_servico = Servico.objects.create(nome="Coleta de digitais")
        cls.equipe = Equipe.objects.create(nome="Equipe Alfa")
        cls.motorista = Motorista.objects.create(nome="Motorista Teste")

        cls.solicitante = User.objects.create_user("solicitante", password="x")
        cls.outro_solicitante = User.objects.create_user("outro", password="x")
        cls.analista = User.objects.create_user("analista", password="x")
        cls.analista.groups.add(Group.objects.create(name=GRUPO_ANALISTA))
        cls.gestor = User.objects.create_user("gestor", password="x")
        cls.gestor.groups.add(Group.objects.create(name=GRUPO_GESTOR_DG))
        cls.superusuario = User.objects.create_superuser("root", password="x")

    def criar_solicitacao(self, **kwargs):
        dados = {
            "data_solicitacao": date(2026, 8, 1),
            "data_inicio_evento": date(2026, 9, 10),
            "data_fim_evento": date(2026, 9, 11),
            "municipio": self.municipio,
            "tipo_evento": self.tipo,
            "orgao_responsavel": self.orgao,
            "solicitante_nome": "Fulano",
            "solicitante_cargo": "Agente",
            "solicitante_unidade": "Unidade X",
            "contato": "41 99999-0000",
            "local_evento": "Praça central",
            "criado_por": self.solicitante,
        }
        dados.update(kwargs)
        solicitacao = SolicitacaoEvento.objects.create(**dados)
        return solicitacao

    def solicitacao_completa(self):
        solicitacao = self.criar_solicitacao()
        solicitacao.itens_servico.create(servico=self.servico)
        return solicitacao

    def dados_completos_post(self, acao="enviar"):
        return {
            "acao": acao,
            "data_solicitacao": "2026-08-01",
            "data_inicio_evento": "2026-09-10",
            "data_fim_evento": "2026-09-11",
            "tipo_evento": self.tipo.pk,
            "municipio": self.municipio.pk,
            "local_evento": "Praça central",
            "solicitante_nome": "Fulano",
            "solicitante_cargo": "Agente",
            "solicitante_unidade": "Unidade X",
            "contato": "41 99999-0000",
            "orgao_responsavel": self.orgao.pk,
            "servicos": [self.servico.pk],
            "unidade_movel": "1",
            "veiculo_exposicao": "0",
        }


class ModelosTests(BaseSolicitacaoTestCase):
    def test_regiao_derivada_do_municipio(self):
        solicitacao = self.criar_solicitacao(regiao=None)
        self.assertEqual(solicitacao.regiao, self.regiao)

    def test_regiao_corrigida_ao_trocar_municipio(self):
        solicitacao = self.criar_solicitacao()
        novo_municipio = Municipio.objects.create(nome="Nova", regiao=self.outra_regiao)
        solicitacao.municipio = novo_municipio
        solicitacao.save()
        self.assertEqual(solicitacao.regiao, self.outra_regiao)

    def test_periodo_invalido_no_clean(self):
        solicitacao = self.criar_solicitacao()
        solicitacao.data_fim_evento = date(2026, 9, 1)
        with self.assertRaises(ValidationError):
            solicitacao.full_clean()

    def test_mes_evento_derivado_da_data_inicio(self):
        solicitacao = self.criar_solicitacao()
        self.assertEqual(solicitacao.mes_evento, 9)
        solicitacao.data_inicio_evento = None
        self.assertIsNone(solicitacao.mes_evento)

    def test_servico_unico_por_solicitacao(self):
        solicitacao = self.solicitacao_completa()
        with self.assertRaises(Exception):
            solicitacao.itens_servico.create(servico=self.servico)

    def test_equipe_unica_por_solicitacao(self):
        solicitacao = self.criar_solicitacao()
        solicitacao.itens_equipe.create(equipe=self.equipe)
        with self.assertRaises(Exception):
            solicitacao.itens_equipe.create(equipe=self.equipe)


class FormsTests(BaseSolicitacaoTestCase):
    def test_rascunho_parcial_valido(self):
        form = SolicitacaoForm({"data_solicitacao": "2026-08-01"}, enviar=False)
        self.assertTrue(form.is_valid(), form.errors)

    def test_envio_incompleto_invalido(self):
        form = SolicitacaoForm({"data_solicitacao": "2026-08-01"}, enviar=True)
        self.assertFalse(form.is_valid())
        self.assertIn("municipio", form.errors)
        self.assertIn("servicos", form.errors)

    def test_envio_completo_valido(self):
        dados = self.dados_completos_post()
        form = SolicitacaoForm(dados, enviar=True)
        self.assertTrue(form.is_valid(), form.errors)

    def test_periodo_invertido_invalido(self):
        dados = self.dados_completos_post()
        dados["data_fim_evento"] = "2026-09-01"
        form = SolicitacaoForm(dados, enviar=True)
        self.assertFalse(form.is_valid())
        self.assertIn("data_fim_evento", form.errors)

    def test_despacho_negativo_exige_observacao(self):
        form = DespachoForm({"decisao": DecisaoDG.NAO_ATENDER, "observacao": ""})
        self.assertFalse(form.is_valid())
        form = DespachoForm({"decisao": DecisaoDG.CANCELADO, "observacao": " "})
        self.assertFalse(form.is_valid())
        form = DespachoForm({"decisao": DecisaoDG.ATENDER, "observacao": ""})
        self.assertTrue(form.is_valid())

    def test_cadastro_inativo_fora_das_opcoes(self):
        inativo = TipoEvento.objects.create(nome="Inativo", ativo=False)
        form = SolicitacaoForm()
        self.assertNotIn(inativo, form.fields["tipo_evento"].queryset)

    def test_cadastro_inativo_vinculado_permanece_visivel(self):
        solicitacao = self.criar_solicitacao()
        self.tipo.ativo = False
        self.tipo.save()
        form = SolicitacaoForm(instance=solicitacao)
        self.assertIn(self.tipo, form.fields["tipo_evento"].queryset)


class WorkflowTests(BaseSolicitacaoTestCase):
    def test_fluxo_completo_valido(self):
        solicitacao = self.solicitacao_completa()
        solicitacao.itens_equipe.create(equipe=self.equipe)
        solicitacao.quantidade_servidores = 5
        solicitacao.tipo_operacao = "ORDINARIA"
        solicitacao.save()

        services.enviar(solicitacao, self.solicitante)
        self.assertEqual(solicitacao.status, StatusSolicitacao.ENVIADA)
        services.iniciar_analise(solicitacao, self.analista)
        self.assertEqual(solicitacao.status, StatusSolicitacao.EM_ANALISE)
        services.encaminhar_para_despacho(solicitacao, self.analista)
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        self.assertEqual(solicitacao.status, StatusSolicitacao.ATENDIDA)
        self.assertEqual(solicitacao.decidido_por, self.gestor)
        self.assertIsNotNone(solicitacao.decidido_em)

    def test_decisoes_definem_status_final(self):
        casos = [
            (DecisaoDG.ATENDER, StatusSolicitacao.ATENDIDA),
            (DecisaoDG.NAO_ATENDER, StatusSolicitacao.NAO_ATENDIDA),
            (DecisaoDG.CANCELADO, StatusSolicitacao.CANCELADA),
        ]
        for decisao, status_final in casos:
            with self.subTest(decisao=decisao):
                solicitacao = self.solicitacao_completa()
                solicitacao.status = StatusSolicitacao.AGUARDANDO_DESPACHO
                solicitacao.save()
                services.despachar(solicitacao, self.gestor, decisao, observacao="Motivo")
                self.assertEqual(solicitacao.status, status_final)

    def test_transicoes_invalidas_rejeitadas(self):
        solicitacao = self.solicitacao_completa()
        with self.assertRaises(services.TransicaoInvalida):
            services.iniciar_analise(solicitacao, self.analista)
        with self.assertRaises(services.TransicaoInvalida):
            services.encaminhar_para_despacho(solicitacao, self.analista)
        with self.assertRaises(services.TransicaoInvalida):
            services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)

    def test_envio_sem_servicos_rejeitado(self):
        solicitacao = self.criar_solicitacao()
        with self.assertRaises(ValidationError):
            services.enviar(solicitacao, self.solicitante)

    def test_encaminhamento_sem_planejamento_rejeitado(self):
        solicitacao = self.solicitacao_completa()
        solicitacao.status = StatusSolicitacao.EM_ANALISE
        solicitacao.save()
        with self.assertRaises(ValidationError):
            services.encaminhar_para_despacho(solicitacao, self.analista)

    def test_despacho_negativo_sem_observacao_rejeitado(self):
        solicitacao = self.solicitacao_completa()
        solicitacao.status = StatusSolicitacao.AGUARDANDO_DESPACHO
        solicitacao.save()
        with self.assertRaises(ValidationError):
            services.despachar(solicitacao, self.gestor, DecisaoDG.NAO_ATENDER)

    def test_sem_novo_despacho_apos_finalizada(self):
        solicitacao = self.solicitacao_completa()
        solicitacao.status = StatusSolicitacao.AGUARDANDO_DESPACHO
        solicitacao.save()
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        with self.assertRaises(services.TransicaoInvalida):
            services.despachar(solicitacao, self.gestor, DecisaoDG.NAO_ATENDER, "x")

    def test_historico_registrado_nas_transicoes(self):
        solicitacao = self.solicitacao_completa()
        solicitacao.itens_equipe.create(equipe=self.equipe)
        solicitacao.quantidade_servidores = 5
        solicitacao.tipo_operacao = "ORDINARIA"
        solicitacao.save()
        services.enviar(solicitacao, self.solicitante)
        services.iniciar_analise(solicitacao, self.analista)
        services.encaminhar_para_despacho(solicitacao, self.analista)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        acoes = list(solicitacao.historico.values_list("acao", flat=True))
        self.assertEqual(
            acoes,
            [
                AcaoHistorico.ENVIO,
                AcaoHistorico.INICIO_ANALISE,
                AcaoHistorico.ENCAMINHAMENTO_DESPACHO,
                AcaoHistorico.DECISAO,
            ],
        )

    def test_timeline_reflete_status(self):
        solicitacao = self.solicitacao_completa()
        etapas = services.montar_timeline(solicitacao)
        self.assertEqual(etapas[0]["titulo"], "Enviar solicitação")
        self.assertEqual(etapas[0]["estado"], "atual")
        solicitacao.status = StatusSolicitacao.ATENDIDA
        etapas = services.montar_timeline(solicitacao)
        self.assertEqual(etapas[-1]["titulo"], "Atendida")
        self.assertTrue(all(e["estado"] == "concluido" for e in etapas))


class ViewsTests(BaseSolicitacaoTestCase):
    def test_login_obrigatorio(self):
        for url in [
            reverse("solicitacoes:lista"),
            reverse("solicitacoes:nova"),
        ]:
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 302)
            self.assertIn("entrar", resposta.headers["Location"])

    def test_criar_rascunho_parcial(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:nova"),
            {"acao": "rascunho", "data_solicitacao": "2026-08-01", "solicitante_nome": "Fulano"},
        )
        solicitacao = SolicitacaoEvento.objects.latest("pk")
        self.assertRedirects(
            resposta, reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertEqual(solicitacao.status, StatusSolicitacao.RASCUNHO)
        self.assertEqual(solicitacao.criado_por, self.solicitante)
        self.assertTrue(
            solicitacao.historico.filter(acao=AcaoHistorico.CRIACAO).exists()
        )

    def test_criar_e_enviar(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:nova"), self.dados_completos_post()
        )
        solicitacao = SolicitacaoEvento.objects.latest("pk")
        self.assertRedirects(
            resposta, reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertEqual(solicitacao.status, StatusSolicitacao.ENVIADA)
        self.assertEqual(list(solicitacao.servicos.all()), [self.servico])

    def test_envio_incompleto_rerenderiza_com_erros(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:nova"),
            {"acao": "enviar", "data_solicitacao": "2026-08-01"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "form-erro")
        self.assertEqual(SolicitacaoEvento.objects.count(), 0)

    def test_edicao_atualiza_sem_duplicar_vinculos(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)
        dados = self.dados_completos_post(acao="rascunho")
        dados["servicos"] = [self.servico.pk, self.outro_servico.pk]
        self.client.post(reverse("solicitacoes:editar", args=[solicitacao.pk]), dados)
        self.assertEqual(solicitacao.itens_servico.count(), 2)
        dados["servicos"] = [self.outro_servico.pk]
        self.client.post(reverse("solicitacoes:editar", args=[solicitacao.pk]), dados)
        self.assertEqual(
            list(solicitacao.servicos.all()), [self.outro_servico]
        )

    def test_rascunho_alheio_inacessivel(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.outro_solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)

    def test_solicitante_nao_edita_apos_envio(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)

    def test_analista_edita_planejamento_e_nao_dados(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.iniciar_analise(solicitacao, self.analista)
        self.client.force_login(self.analista)
        resposta = self.client.post(
            reverse("solicitacoes:editar", args=[solicitacao.pk]),
            {
                "acao": "rascunho",
                "equipes": [self.equipe.pk],
                "quantidade_servidores": 4,
                "tipo_operacao": "ORDINARIA",
                "motorista": self.motorista.pk,
                "solicitante_nome": "Hackeado",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.quantidade_servidores, 4)
        self.assertEqual(list(solicitacao.equipes.all()), [self.equipe])
        # Campos fora do planejamento não podem ser alterados pelo analista.
        self.assertEqual(solicitacao.solicitante_nome, "Fulano")
        self.assertTrue(
            solicitacao.historico.filter(acao=AcaoHistorico.PLANEJAMENTO).exists()
        )

    def test_transicoes_exigem_post(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.analista)
        resposta = self.client.get(
            reverse("solicitacoes:iniciar_analise", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 405)

    def test_perfis_nas_transicoes(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:iniciar_analise", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)
        self.client.force_login(self.gestor)
        resposta = self.client.post(
            reverse("solicitacoes:iniciar_analise", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)
        self.client.force_login(self.analista)
        resposta = self.client.post(
            reverse("solicitacoes:iniciar_analise", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 302)

    def test_despacho_via_view(self):
        solicitacao = self.solicitacao_completa()
        solicitacao.status = StatusSolicitacao.AGUARDANDO_DESPACHO
        solicitacao.save()
        self.client.force_login(self.gestor)
        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[solicitacao.pk]),
            {"decisao": "NAO_ATENDER", "observacao": "Sem equipe disponível"},
        )
        self.assertEqual(resposta.status_code, 302)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.NAO_ATENDIDA)

    def test_superusuario_ignora_restricoes(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.superusuario)
        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 200)

    def test_lista_filtros_e_paginacao(self):
        for indice in range(18):
            self.criar_solicitacao(local_evento=f"Local {indice}")
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)

        resposta = self.client.get(reverse("solicitacoes:lista"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(resposta.context["pagina"]), 15)

        resposta = self.client.get(reverse("solicitacoes:lista"), {"pagina": 2})
        self.assertEqual(len(resposta.context["pagina"]), 4)

        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"status": StatusSolicitacao.ENVIADA}
        )
        self.assertEqual(resposta.context["pagina"].paginator.count, 1)

        resposta = self.client.get(reverse("solicitacoes:lista"), {"q": "Local 7"})
        self.assertEqual(resposta.context["pagina"].paginator.count, 1)

        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"municipio": self.municipio.pk}
        )
        self.assertEqual(resposta.context["pagina"].paginator.count, 19)

    def test_lista_respeita_visibilidade(self):
        rascunho = self.criar_solicitacao()
        enviada = self.solicitacao_completa()
        services.enviar(enviada, self.solicitante)
        self.client.force_login(self.analista)
        resposta = self.client.get(reverse("solicitacoes:lista"))
        pks = [linha["solicitacao"].pk for linha in resposta.context["linhas"]]
        self.assertIn(enviada.pk, pks)
        self.assertNotIn(rascunho.pk, pks)
