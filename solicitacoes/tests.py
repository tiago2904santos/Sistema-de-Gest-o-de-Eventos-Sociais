import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from cadastros.models import (
    Equipe,
    Estado,
    Motorista,
    Municipio,
    OrgaoResponsavel,
    Regiao,
    Servico,
    TipoEvento,
    UnidadeMovel,
)

from .forms import DespachoForm, SolicitacaoForm
from .models import (
    AcaoHistorico,
    DecisaoDG,
    SolicitacaoEvento,
    StatusSolicitacao,
)
from .permissions import GRUPO_ADMINISTRADOR, GRUPO_GESTOR_DG
from . import services

User = get_user_model()


class BaseSolicitacaoTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.regiao = Regiao.objects.create(nome="Região Teste")
        cls.outra_regiao = Regiao.objects.create(nome="Outra Região")
        cls.estado = Estado.objects.get(codigo_ibge=41)
        cls.outro_estado = Estado.objects.create(
            nome="São Paulo", sigla="SP", codigo_ibge=35
        )
        cls.municipio = Municipio.objects.create(
            nome="Cidade Teste", estado=cls.estado, regiao=cls.regiao
        )
        cls.tipo = TipoEvento.objects.create(nome="Ação social")
        cls.tipo_parana_em_acao = TipoEvento.objects.create(nome="Paraná em Ação")
        cls.orgao = OrgaoResponsavel.objects.create(nome="Órgão Teste")
        cls.servico = Servico.objects.create(nome="Emissão de CIN")
        cls.outro_servico = Servico.objects.create(nome="Coleta de digitais")
        cls.equipe = Equipe.objects.create(nome="Equipe Alfa")
        cls.outra_equipe = Equipe.objects.create(nome="IIPR")
        cls.motorista = Motorista.objects.create(nome="Motorista Teste")
        cls.van = UnidadeMovel.objects.create(nome="Van CIN 01")

        cls.solicitante = User.objects.create_user("solicitante", password="x")
        cls.outro_solicitante = User.objects.create_user("outro", password="x")
        cls.gestor = User.objects.create_user("gestor", password="x")
        cls.gestor.groups.add(Group.objects.create(name=GRUPO_GESTOR_DG))
        cls.administrador = User.objects.create_user("administrador", password="x")
        cls.administrador.groups.add(Group.objects.create(name=GRUPO_ADMINISTRADOR))
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
            "solicitante_cargo_unidade": "Agente / Unidade X",
            "contato": "41 99999-0000",
            "local_evento": "Praça central",
            "criado_por": self.solicitante,
        }
        dados.update(kwargs)
        solicitacao = SolicitacaoEvento.objects.create(**dados)
        return solicitacao

    def solicitacao_completa(self):
        """Solicitação pronta para envio: serviços e planejamento preenchidos."""
        solicitacao = self.criar_solicitacao()
        solicitacao.itens_servico.create(servico=self.servico)
        solicitacao.itens_equipe.create(equipe=self.equipe, quantidade_servidores=5)
        return solicitacao

    def dados_completos_post(self, acao="enviar"):
        return {
            "acao": acao,
            "data_solicitacao": "2026-08-01",
            "data_inicio_evento": "2026-09-10",
            "data_fim_evento": "2026-09-11",
            "tipo_evento": self.tipo.pk,
            "estado": self.estado.pk,
            "municipio": self.municipio.pk,
            "local_evento": "Praça central",
            "solicitante_nome": "Fulano",
            "solicitante_cargo_unidade": "Agente / Unidade X",
            "contato": "41 99999-0000",
            "orgao_responsavel": self.orgao.pk,
            "servicos": [self.servico.pk],
            "equipes": [self.equipe.pk],
            f"quantidade_equipe_{self.equipe.pk}": 4,
            "tipo_operacao": "DIARIA",
            "unidade_movel": "1",
            "unidade_movel_designada": self.van.pk,
            "veiculo_exposicao": "0",
        }


class ModelosTests(BaseSolicitacaoTestCase):
    def test_tipo_operacao_padrao_e_diaria(self):
        solicitacao = self.criar_solicitacao()
        self.assertEqual(solicitacao.tipo_operacao, "DIARIA")
        self.assertEqual(solicitacao.get_tipo_operacao_display(), "Diária")

    def test_regiao_derivada_do_municipio(self):
        solicitacao = self.criar_solicitacao(regiao=None)
        self.assertEqual(solicitacao.regiao, self.regiao)

    def test_regiao_corrigida_ao_trocar_municipio(self):
        solicitacao = self.criar_solicitacao()
        novo_municipio = Municipio.objects.create(
            nome="Nova", estado=self.outro_estado, regiao=self.outra_regiao
        )
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
        solicitacao.itens_equipe.create(equipe=self.equipe, quantidade_servidores=5)
        with self.assertRaises(Exception):
            solicitacao.itens_equipe.create(equipe=self.equipe)


class FormsTests(BaseSolicitacaoTestCase):
    def test_estado_padrao_e_parana(self):
        form = SolicitacaoForm()
        self.assertEqual(form.initial["estado"], self.estado.pk)

    def test_rascunho_parcial_valido(self):
        form = SolicitacaoForm({"data_solicitacao": "2026-08-01"}, enviar=False)
        self.assertTrue(form.is_valid(), form.errors)

    def test_envio_incompleto_invalido(self):
        form = SolicitacaoForm({"data_solicitacao": "2026-08-01"}, enviar=True)
        self.assertFalse(form.is_valid())
        self.assertIn("municipio", form.errors)
        self.assertIn("servicos", form.errors)
        self.assertIn("equipes", form.errors)

    def test_envio_completo_valido(self):
        dados = self.dados_completos_post()
        form = SolicitacaoForm(dados, enviar=True)
        self.assertTrue(form.is_valid(), form.errors)

    def test_envio_exige_quantidade_por_equipe(self):
        dados = self.dados_completos_post()
        dados[f"quantidade_equipe_{self.equipe.pk}"] = ""
        form = SolicitacaoForm(dados, enviar=True)
        self.assertFalse(form.is_valid())
        self.assertIn("equipes", form.errors)

    def test_contato_nao_e_obrigatorio_para_envio(self):
        dados = self.dados_completos_post()
        dados["contato"] = ""

        form = SolicitacaoForm(dados, enviar=True)

        self.assertTrue(form.is_valid(), form.errors)

    def test_local_do_evento_nao_e_obrigatorio_para_envio(self):
        dados = self.dados_completos_post()
        dados["local_evento"] = ""

        form = SolicitacaoForm(dados, enviar=True)

        self.assertTrue(form.is_valid(), form.errors)

    def test_parana_em_acao_define_solicitante_e_cargo_unidade(self):
        dados = self.dados_completos_post()
        dados["tipo_evento"] = self.tipo_parana_em_acao.pk
        dados["solicitante_nome"] = "Outro solicitante"
        dados["solicitante_cargo_unidade"] = "Outro cargo"

        form = SolicitacaoForm(dados, enviar=True)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["solicitante_nome"], "Paraná em Ação")
        self.assertEqual(form.cleaned_data["solicitante_cargo_unidade"], "SEJU")

    def test_municipio_deve_pertencer_ao_estado(self):
        dados = self.dados_completos_post()
        dados["estado"] = self.outro_estado.pk

        form = SolicitacaoForm(dados, enviar=True)

        self.assertFalse(form.is_valid())
        self.assertIn("municipio", form.errors)

    def test_periodo_invertido_invalido(self):
        dados = self.dados_completos_post()
        dados["data_fim_evento"] = "2026-09-01"
        form = SolicitacaoForm(dados, enviar=True)
        self.assertFalse(form.is_valid())
        self.assertIn("data_fim_evento", form.errors)

    def test_motorista_apenas_com_unidade_movel(self):
        dados = self.dados_completos_post(acao="rascunho")
        dados["unidade_movel"] = "0"
        dados["motorista"] = self.motorista.pk

        form = SolicitacaoForm(dados, enviar=False)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["motorista"])

        dados["unidade_movel"] = "1"
        form = SolicitacaoForm(dados, enviar=False)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["motorista"], self.motorista)

    def test_edicao_limpa_motorista_sem_unidade_movel(self):
        solicitacao = self.criar_solicitacao(
            unidade_movel=True, motorista=self.motorista
        )
        dados = self.dados_completos_post(acao="rascunho")
        dados["unidade_movel"] = "0"
        dados["motorista"] = self.motorista.pk
        form = SolicitacaoForm(dados, instance=solicitacao, enviar=False)
        self.assertTrue(form.is_valid(), form.errors)
        solicitacao = form.save()
        self.assertIsNone(solicitacao.motorista)
        self.assertFalse(solicitacao.unidade_movel)

    def test_envio_com_unidade_movel_exige_qual_unidade(self):
        dados = self.dados_completos_post()
        dados["unidade_movel_designada"] = ""
        form = SolicitacaoForm(dados, enviar=True)
        self.assertFalse(form.is_valid())
        self.assertIn("unidade_movel_designada", form.errors)

    def test_sem_unidade_movel_limpa_designada_e_motorista(self):
        dados = self.dados_completos_post(acao="rascunho")
        dados["unidade_movel"] = "0"
        dados["motorista"] = self.motorista.pk

        form = SolicitacaoForm(dados, enviar=False)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["unidade_movel_designada"])
        self.assertIsNone(form.cleaned_data["motorista"])

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
        """Rascunho → envio → deferida em andamento → confirmação do solicitante."""
        solicitacao = self.solicitacao_completa()

        services.enviar(solicitacao, self.solicitante)
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        self.assertEqual(
            solicitacao.status, StatusSolicitacao.DEFERIDA_EM_ANDAMENTO
        )
        self.assertEqual(solicitacao.decidido_por, self.gestor)
        self.assertIsNotNone(solicitacao.decidido_em)
        # Depois do evento, o solicitante confirma o atendimento.
        services.concluir_atendimento(solicitacao, self.solicitante)
        self.assertEqual(solicitacao.status, StatusSolicitacao.ATENDIDA)
        self.assertTrue(
            solicitacao.historico.filter(acao=AcaoHistorico.CONCLUSAO).exists()
        )

    def test_decisoes_definem_status_final(self):
        casos = [
            (DecisaoDG.ATENDER, StatusSolicitacao.DEFERIDA_EM_ANDAMENTO),
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
        # Rascunho não pode ser despachado.
        with self.assertRaises(services.TransicaoInvalida):
            services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        # Solicitação já enviada não pode ser enviada de novo.
        services.enviar(solicitacao, self.solicitante)
        with self.assertRaises(services.TransicaoInvalida):
            services.enviar(solicitacao, self.solicitante)

    def test_envio_sem_servicos_rejeitado(self):
        solicitacao = self.criar_solicitacao()
        solicitacao.itens_equipe.create(equipe=self.equipe, quantidade_servidores=5)
        with self.assertRaises(ValidationError):
            services.enviar(solicitacao, self.solicitante)

    def test_envio_sem_equipe_rejeitado(self):
        solicitacao = self.criar_solicitacao()
        solicitacao.itens_servico.create(servico=self.servico)
        with self.assertRaises(ValidationError):
            services.enviar(solicitacao, self.solicitante)

    def test_envio_sem_quantidade_por_equipe_rejeitado(self):
        solicitacao = self.criar_solicitacao()
        solicitacao.itens_servico.create(servico=self.servico)
        solicitacao.itens_equipe.create(equipe=self.equipe, quantidade_servidores=None)
        with self.assertRaises(ValidationError):
            services.enviar(solicitacao, self.solicitante)

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

    def test_dg_ajusta_quantidade_de_servidores_ao_despachar(self):
        solicitacao = self.solicitacao_completa()
        solicitacao.itens_equipe.create(
            equipe=self.outra_equipe, quantidade_servidores=4
        )
        services.enviar(solicitacao, self.solicitante)

        item_alfa = solicitacao.itens_equipe.get(equipe=self.equipe)
        services.despachar(
            solicitacao,
            self.gestor,
            DecisaoDG.ATENDER,
            quantidades={self.equipe.pk: 3, self.outra_equipe.pk: 4},
        )

        item_alfa.refresh_from_db()
        solicitacao.refresh_from_db()
        self.assertEqual(item_alfa.quantidade_servidores, 3)
        self.assertEqual(solicitacao.quantidade_servidores, 7)
        registro = solicitacao.historico.get(acao=AcaoHistorico.AJUSTE_DG)
        self.assertIn("Equipe Alfa: 5 → 3", registro.observacao)
        # A equipe aceita sem mudança não entra no registro.
        self.assertNotIn("IIPR", registro.observacao)

    def test_despacho_sem_ajuste_nao_registra_ajuste(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.despachar(
            solicitacao,
            self.gestor,
            DecisaoDG.ATENDER,
            quantidades={self.equipe.pk: 5},
        )
        self.assertFalse(
            solicitacao.historico.filter(acao=AcaoHistorico.AJUSTE_DG).exists()
        )

    def test_ajuste_da_dg_com_quantidade_invalida_rejeitado(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        with self.assertRaises(ValidationError):
            services.despachar(
                solicitacao,
                self.gestor,
                DecisaoDG.ATENDER,
                quantidades={self.equipe.pk: 0},
            )
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        self.assertEqual(
            solicitacao.itens_equipe.get(equipe=self.equipe).quantidade_servidores, 5
        )

    def test_dg_salva_ajustes_sem_decidir(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)

        mudancas = services.salvar_ajustes_dg(
            solicitacao, self.gestor, {self.equipe.pk: 2}
        )

        self.assertEqual(len(mudancas), 1)
        solicitacao.refresh_from_db()
        # Continua aguardando despacho — só as quantidades mudaram.
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        self.assertEqual(solicitacao.quantidade_servidores, 2)
        self.assertTrue(
            solicitacao.historico.filter(acao=AcaoHistorico.AJUSTE_DG).exists()
        )

    def test_salvar_ajustes_apenas_aguardando_despacho(self):
        solicitacao = self.solicitacao_completa()
        with self.assertRaises(services.TransicaoInvalida):
            services.salvar_ajustes_dg(solicitacao, self.gestor, {self.equipe.pk: 2})

    def test_concluir_apenas_deferida_em_andamento(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        with self.assertRaises(services.TransicaoInvalida):
            services.concluir_atendimento(solicitacao, self.solicitante)

    def test_cancelamento_do_evento_com_motivo(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)

        services.cancelar_evento(
            solicitacao, self.outro_solicitante, "Chuva forte no dia do evento."
        )

        self.assertEqual(solicitacao.status, StatusSolicitacao.CANCELADA)
        registro = solicitacao.historico.get(acao=AcaoHistorico.CANCELAMENTO)
        self.assertEqual(registro.observacao, "Chuva forte no dia do evento.")
        self.assertEqual(registro.usuario, self.outro_solicitante)

    def test_cancelamento_exige_motivo(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        with self.assertRaises(ValidationError):
            services.cancelar_evento(solicitacao, self.solicitante, "   ")
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)

    def test_cancelamento_nao_se_aplica_a_finalizadas_nem_rascunho(self):
        rascunho = self.criar_solicitacao()
        with self.assertRaises(services.TransicaoInvalida):
            services.cancelar_evento(rascunho, self.solicitante, "Motivo")

        finalizada = self.solicitacao_completa()
        finalizada.status = StatusSolicitacao.NAO_ATENDIDA
        finalizada.save()
        with self.assertRaises(services.TransicaoInvalida):
            services.cancelar_evento(finalizada, self.solicitante, "Motivo")

    def test_devolucao_para_ajuste_e_reenvio(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.devolver(solicitacao, self.gestor, "Falta detalhar o local.")
        self.assertEqual(solicitacao.status, StatusSolicitacao.DEVOLVIDA)
        registro = solicitacao.historico.get(acao=AcaoHistorico.DEVOLUCAO)
        self.assertEqual(registro.observacao, "Falta detalhar o local.")
        # Depois do ajuste, o criador reenvia e a DG decide normalmente.
        services.enviar(solicitacao, self.solicitante)
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        self.assertEqual(
            solicitacao.status, StatusSolicitacao.DEFERIDA_EM_ANDAMENTO
        )

    def test_devolucao_exige_observacao(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        with self.assertRaises(ValidationError):
            services.devolver(solicitacao, self.gestor, "  ")
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)

    def test_devolucao_apenas_aguardando_despacho(self):
        solicitacao = self.solicitacao_completa()
        with self.assertRaises(services.TransicaoInvalida):
            services.devolver(solicitacao, self.gestor, "Motivo")

    def test_devolvida_e_editavel_pelo_criador(self):
        from . import permissions as perms

        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.devolver(solicitacao, self.gestor, "Ajustar período.")
        self.assertTrue(perms.pode_editar_dados(self.solicitante, solicitacao))
        self.assertTrue(perms.pode_enviar(self.solicitante, solicitacao))
        # Devolvida não é rascunho: continua visível e não pode ser excluída.
        self.assertTrue(perms.pode_ver(self.outro_solicitante, solicitacao))
        self.assertFalse(perms.pode_excluir(self.solicitante, solicitacao))

    def test_timeline_devolvida_reabre_primeira_etapa(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.devolver(solicitacao, self.gestor, "Ajustar equipe.")
        etapas = services.montar_timeline(solicitacao)
        self.assertEqual(etapas[0]["estado"], "atual")
        self.assertIn("Devolvida", etapas[0]["subtitulo"])

    def test_historico_registrado_nas_transicoes(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        acoes = list(solicitacao.historico.values_list("acao", flat=True))
        self.assertEqual(acoes, [AcaoHistorico.ENVIO, AcaoHistorico.DECISAO])
        self.assertEqual(solicitacao.historico.last().rotulo_status, "Atender")

    def test_historico_converte_status_final_em_decisao_da_dg(self):
        solicitacao = self.solicitacao_completa()
        rotulos = {
            StatusSolicitacao.ATENDIDA: "Atender",
            StatusSolicitacao.NAO_ATENDIDA: "Não atender",
            StatusSolicitacao.CANCELADA: "Evento cancelado",
        }

        for status, rotulo in rotulos.items():
            registro = solicitacao.historico.create(
                usuario=self.gestor,
                acao=AcaoHistorico.DECISAO,
                status_novo=status,
            )
            self.assertEqual(registro.rotulo_status, rotulo)

    def test_historico_legado_continua_legivel(self):
        solicitacao = self.solicitacao_completa()
        registro = solicitacao.historico.create(
            usuario=self.solicitante,
            acao=AcaoHistorico.INICIO_ANALISE,
            status_novo="EM_ANALISE",
        )
        self.assertEqual(registro.rotulo_status, "Em análise")

    def test_timeline_reflete_status(self):
        solicitacao = self.solicitacao_completa()
        etapas = services.montar_timeline(solicitacao)
        self.assertEqual(etapas[0]["titulo"], "Enviar para a DG")
        self.assertEqual(etapas[0]["estado"], "atual")

        solicitacao.status = StatusSolicitacao.AGUARDANDO_DESPACHO
        etapas = services.montar_timeline(solicitacao)
        self.assertEqual(etapas[1]["estado"], "atual")

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

    def test_botao_salvar_rascunho_ignora_validacao_nativa(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:nova"))

        self.assertContains(
            resposta,
            'name="acao" value="rascunho" formnovalidate',
        )

    def test_contato_usa_mascara_de_telefone(self):
        self.client.force_login(self.solicitante)

        resposta = self.client.get(reverse("solicitacoes:nova"))

        self.assertContains(resposta, 'name="contato"')
        self.assertContains(resposta, 'inputmode="tel"')
        self.assertContains(resposta, 'maxlength="15"')
        self.assertContains(resposta, "data-mask-telefone")

    def test_formulario_unico_tem_planejamento(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:nova"))
        self.assertContains(resposta, "Planejamento operacional")
        self.assertContains(resposta, 'name="equipes"')

    def test_criar_e_enviar_para_dg(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:nova"), self.dados_completos_post()
        )
        solicitacao = SolicitacaoEvento.objects.latest("pk")
        self.assertRedirects(
            resposta, reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        self.assertEqual(list(solicitacao.servicos.all()), [self.servico])
        self.assertEqual(list(solicitacao.equipes.all()), [self.equipe])
        self.assertEqual(solicitacao.quantidade_servidores, 4)

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

    def test_dados_travam_apos_envio(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)
        resposta = self.client.post(
            reverse("solicitacoes:editar", args=[solicitacao.pk]),
            {"acao": "rascunho", "solicitante_nome": "Hackeado"},
        )
        self.assertEqual(resposta.status_code, 403)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.solicitante_nome, "Fulano")

    def test_secao_despacho_dg_fica_oculta_para_quem_nao_e_dg(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)

        resposta = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertNotContains(resposta, ">Despacho DG<", html=False)

        services.enviar(solicitacao, self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertNotContains(resposta, ">Despacho DG<", html=False)

    def test_secao_despacho_dg_nao_aparece_no_cadastro_nem_para_administrador(self):
        self.client.force_login(self.superusuario)

        resposta = self.client.get(reverse("solicitacoes:nova"))

        self.assertNotContains(resposta, ">Despacho DG<", html=False)
        self.assertNotContains(resposta, 'name="decisao_dg_visual"')

    def test_secao_despacho_dg_fica_visivel_para_gestor_dg(self):
        solicitacao = self.solicitacao_completa()
        solicitacao.status = StatusSolicitacao.AGUARDANDO_DESPACHO
        solicitacao.save()
        self.client.force_login(self.gestor)

        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertContains(resposta, ">Despacho DG<", html=False)

    def test_transicoes_exigem_post(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:enviar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 405)

    def test_enviar_pelo_detalhe(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:enviar", args=[solicitacao.pk])
        )
        self.assertRedirects(
            resposta, reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        self.assertTrue(
            solicitacao.historico.filter(acao=AcaoHistorico.ENVIO).exists()
        )

    def test_apenas_criador_envia(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.gestor)
        resposta = self.client.post(
            reverse("solicitacoes:enviar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)

    def test_apenas_gestor_dg_despacha(self):
        """Administrador gerencia logins, mas não tem alçada de despacho."""
        solicitacao = self.solicitacao_completa()
        solicitacao.status = StatusSolicitacao.AGUARDANDO_DESPACHO
        solicitacao.save()
        dados = {"decisao": "ATENDER", "observacao": ""}
        for usuario in [self.solicitante, self.administrador]:
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                resposta = self.client.post(
                    reverse("solicitacoes:despachar", args=[solicitacao.pk]), dados
                )
                self.assertEqual(resposta.status_code, 403)
        self.client.force_login(self.gestor)
        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[solicitacao.pk]), dados
        )
        self.assertEqual(resposta.status_code, 302)
        solicitacao.refresh_from_db()
        self.assertEqual(
            solicitacao.status, StatusSolicitacao.DEFERIDA_EM_ANDAMENTO
        )

    def test_criador_exclui_rascunho(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:excluir", args=[solicitacao.pk])
        )
        self.assertRedirects(resposta, reverse("solicitacoes:lista"))
        self.assertFalse(
            SolicitacaoEvento.objects.filter(pk=solicitacao.pk).exists()
        )

    def test_exclusao_exige_post(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:excluir", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 405)
        self.assertTrue(
            SolicitacaoEvento.objects.filter(pk=solicitacao.pk).exists()
        )

    def test_solicitacao_enviada_nao_pode_ser_excluida(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:excluir", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(
            SolicitacaoEvento.objects.filter(pk=solicitacao.pk).exists()
        )

    def test_rascunho_alheio_nao_pode_ser_excluido(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.outro_solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:excluir", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(
            SolicitacaoEvento.objects.filter(pk=solicitacao.pk).exists()
        )

    def test_botao_excluir_aparece_apenas_no_rascunho_proprio(self):
        rascunho = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:lista"), {"fila": "rascunhos"})
        self.assertContains(resposta, f"/solicitacoes/{rascunho.pk}/excluir/")

        enviada = self.solicitacao_completa()
        services.enviar(enviada, self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:lista"))
        self.assertNotContains(resposta, f"/solicitacoes/{enviada.pk}/excluir/")

    def test_lista_mostra_fila_e_acao_contextual(self):
        rascunho = self.criar_solicitacao()
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)

        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:lista"))
        self.assertContains(resposta, "Meus rascunhos")
        self.assertNotContains(resposta, "Aguardando despacho</a>")
        self.assertContains(resposta, ">Continuar<", html=False)

        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"fila": "rascunhos"}
        )
        self.assertEqual(resposta.context["pagina"].paginator.count, 1)

        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("solicitacoes:lista"))
        self.assertContains(resposta, "Aguardando despacho")
        self.assertContains(resposta, ">Despachar<", html=False)
        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"fila": "despacho"}
        )
        self.assertEqual(resposta.context["pagina"].paginator.count, 1)

    def test_devolucao_via_view(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.gestor)
        # Sem motivo, a devolução é recusada.
        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[solicitacao.pk]),
            {"decisao": "DEVOLVER", "observacao": ""},
        )
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)

        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[solicitacao.pk]),
            {"decisao": "DEVOLVER", "observacao": "Detalhar o local do evento."},
        )
        self.assertEqual(resposta.status_code, 302)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.DEVOLVIDA)

        # O criador reenvia pela própria tela de detalhe.
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:enviar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 302)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)

    def test_fila_devolvidas_na_lista(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.devolver(solicitacao, self.gestor, "Ajustar datas.")
        self.client.force_login(self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"fila": "devolvidas"}
        )
        self.assertEqual(resposta.context["pagina"].paginator.count, 1)
        self.assertContains(resposta, "Devolvidas para ajuste")
        self.assertContains(resposta, ">Continuar<", html=False)

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

    def test_despacho_via_view_com_ajuste_de_quantidade(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.gestor)

        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertContains(resposta, f'name="quantidade_dg_{self.equipe.pk}"')
        self.assertContains(resposta, "Quantidade de servidores por equipe")

        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[solicitacao.pk]),
            {
                "decisao": "ATENDER",
                "observacao": "",
                f"quantidade_dg_{self.equipe.pk}": 2,
            },
        )
        self.assertEqual(resposta.status_code, 302)
        solicitacao.refresh_from_db()
        self.assertEqual(
            solicitacao.status, StatusSolicitacao.DEFERIDA_EM_ANDAMENTO
        )
        self.assertEqual(solicitacao.quantidade_servidores, 2)
        self.assertTrue(
            solicitacao.historico.filter(acao=AcaoHistorico.AJUSTE_DG).exists()
        )

    def test_salvar_ajustes_via_view_sem_decidir(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.gestor)

        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertContains(resposta, "Salvar ajustes")

        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[solicitacao.pk]),
            {
                "acao_despacho": "salvar_ajustes",
                f"quantidade_dg_{self.equipe.pk}": 3,
            },
        )
        self.assertEqual(resposta.status_code, 302)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        self.assertEqual(solicitacao.quantidade_servidores, 3)

        # Depois a DG decide normalmente, sem repetir o ajuste.
        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[solicitacao.pk]),
            {"decisao": "ATENDER", "observacao": ""},
        )
        solicitacao.refresh_from_db()
        self.assertEqual(
            solicitacao.status, StatusSolicitacao.DEFERIDA_EM_ANDAMENTO
        )
        self.assertEqual(solicitacao.quantidade_servidores, 3)

    def test_salvar_ajustes_exige_gestor(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[solicitacao.pk]),
            {
                "acao_despacho": "salvar_ajustes",
                f"quantidade_dg_{self.equipe.pk}": 3,
            },
        )
        self.assertEqual(resposta.status_code, 403)

    def test_solicitante_confirma_atendimento_via_view(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)

        # A tela do criador mostra o botão e a seção de encerramento.
        self.client.force_login(self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertContains(resposta, "Confirmar atendimento")
        self.assertContains(resposta, "Encerramento do evento")

        # Outro usuário não pode confirmar pelo criador.
        self.client.force_login(self.outro_solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:concluir", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)

        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:concluir", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 302)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.ATENDIDA)

    def test_qualquer_usuario_cancela_evento_via_view(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.outro_solicitante)

        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertContains(resposta, "Registrar cancelamento do evento")

        # Sem motivo, nada muda.
        resposta = self.client.post(
            reverse("solicitacoes:cancelar_evento", args=[solicitacao.pk]),
            {"motivo_cancelamento": ""},
        )
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)

        resposta = self.client.post(
            reverse("solicitacoes:cancelar_evento", args=[solicitacao.pk]),
            {"motivo_cancelamento": "Evento cancelado pela prefeitura."},
        )
        self.assertEqual(resposta.status_code, 302)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.CANCELADA)

    def test_fila_deferidas_em_andamento(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        self.client.force_login(self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"fila": "andamento"}
        )
        self.assertEqual(resposta.context["pagina"].paginator.count, 1)
        self.assertContains(resposta, "Deferidas em andamento")
        self.assertContains(resposta, ">Confirmar<", html=False)

    def test_campo_qual_unidade_movel_no_formulario(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:nova"))
        self.assertContains(resposta, 'name="unidade_movel_designada"')
        self.assertContains(resposta, "Van CIN 01")

    def test_cadastro_de_unidades_moveis_disponivel(self):
        self.client.force_login(self.administrador)
        resposta = self.client.get(
            reverse("cadastros:lista", args=["unidades-moveis"])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Van CIN 01")

    def test_superusuario_ignora_restricoes(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.superusuario)
        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 200)

    def test_detalhe_reutiliza_formulario_em_modo_somente_leitura(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)

        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )

        self.assertTrue(resposta.context["somente_leitura"])
        self.assertContains(resposta, "Dados da solicitação")
        self.assertContains(resposta, "Serviços e estrutura do evento")
        self.assertContains(resposta, "Planejamento operacional")
        self.assertContains(resposta, 'name="solicitante_nome"', html=False)
        self.assertContains(resposta, "disabled", html=False)
        self.assertNotContains(resposta, "Salvar rascunho")
        self.assertContains(resposta, "Enviar para a DG")

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
            reverse("solicitacoes:lista"),
            {"status": StatusSolicitacao.AGUARDANDO_DESPACHO},
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
        self.client.force_login(self.outro_solicitante)
        resposta = self.client.get(reverse("solicitacoes:lista"))
        pks = [linha["solicitacao"].pk for linha in resposta.context["linhas"]]
        self.assertIn(enviada.pk, pks)
        self.assertNotIn(rascunho.pk, pks)


class ExportacaoCsvTests(BaseSolicitacaoTestCase):
    def test_exporta_lista_filtrada(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        outra = self.criar_solicitacao(local_evento="Escola municipal")
        self.client.force_login(self.solicitante)

        resposta = self.client.get(reverse("solicitacoes:exportar"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", resposta["Content-Disposition"])
        conteudo = resposta.content.decode("utf-8-sig")
        self.assertIn("Aguardando despacho", conteudo)
        self.assertIn("Equipe Alfa (5)", conteudo)
        self.assertIn("Escola municipal", conteudo)

        # O filtro de status vale também na exportação.
        resposta = self.client.get(
            reverse("solicitacoes:exportar"),
            {"status": StatusSolicitacao.RASCUNHO},
        )
        conteudo = resposta.content.decode("utf-8-sig")
        self.assertIn("Escola municipal", conteudo)
        self.assertNotIn("Aguardando despacho", conteudo)

    def test_exportacao_respeita_visibilidade(self):
        rascunho_alheio = self.criar_solicitacao()
        self.client.force_login(self.outro_solicitante)
        resposta = self.client.get(reverse("solicitacoes:exportar"))
        conteudo = resposta.content.decode("utf-8-sig")
        # Só o cabeçalho: rascunho de outro usuário não sai no CSV.
        self.assertEqual(len(conteudo.strip().splitlines()), 1)

    def test_exportacao_exige_login(self):
        resposta = self.client.get(reverse("solicitacoes:exportar"))
        self.assertEqual(resposta.status_code, 302)


_MEDIA_TESTES = tempfile.mkdtemp(prefix="anexos-teste-")


@override_settings(MEDIA_ROOT=_MEDIA_TESTES)
class AnexosTests(BaseSolicitacaoTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA_TESTES, ignore_errors=True)

    def arquivo(self, nome="oficio.pdf", conteudo=b"%PDF-1.4 teste"):
        return SimpleUploadedFile(nome, conteudo, content_type="application/pdf")

    def test_upload_direto_no_cadastro_da_solicitacao(self):
        self.client.force_login(self.solicitante)
        dados = self.dados_completos_post(acao="rascunho")
        dados["anexos"] = [
            self.arquivo("oficio.pdf"),
            self.arquivo("memorando.pdf", b"%PDF-1.4 memo"),
        ]
        resposta = self.client.post(reverse("solicitacoes:nova"), dados)
        solicitacao = SolicitacaoEvento.objects.latest("pk")
        self.assertRedirects(
            resposta, reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertEqual(solicitacao.anexos.count(), 2)
        self.assertEqual(
            sorted(solicitacao.anexos.values_list("nome_original", flat=True)),
            ["memorando.pdf", "oficio.pdf"],
        )

    def test_upload_invalido_no_cadastro_nao_salva_nada(self):
        self.client.force_login(self.solicitante)
        dados = self.dados_completos_post(acao="rascunho")
        dados["anexos"] = [SimpleUploadedFile("virus.exe", b"MZ")]
        resposta = self.client.post(reverse("solicitacoes:nova"), dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(SolicitacaoEvento.objects.count(), 0)

    def test_campo_de_upload_na_tela_de_cadastro(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:nova"))
        self.assertContains(resposta, 'name="anexos" multiple')
        self.assertContains(resposta, 'enctype="multipart/form-data"')

    def test_criador_anexa_no_rascunho(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )
        self.assertRedirects(
            resposta, reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        anexo = solicitacao.anexos.get()
        self.assertEqual(anexo.nome_original, "oficio.pdf")
        self.assertGreater(anexo.tamanho, 0)
        self.assertEqual(anexo.enviado_por, self.solicitante)
        self.assertTrue(
            solicitacao.historico.filter(
                observacao__contains="Anexo adicionado: oficio.pdf"
            ).exists()
        )

    def test_extensao_proibida_e_rejeitada(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": SimpleUploadedFile("virus.exe", b"MZ")},
        )
        self.assertEqual(solicitacao.anexos.count(), 0)

    def test_arquivo_grande_e_rejeitado(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        gigante = SimpleUploadedFile("grande.pdf", b"x" * (10 * 1024 * 1024 + 1))
        self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": gigante},
        )
        self.assertEqual(solicitacao.anexos.count(), 0)

    def test_anexo_bloqueado_apos_envio(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )
        self.assertEqual(resposta.status_code, 403)

    def test_download_respeita_visibilidade(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )
        anexo = solicitacao.anexos.get()
        url = reverse("solicitacoes:anexo_baixar", args=[solicitacao.pk, anexo.pk])

        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b"".join(resposta.streaming_content), b"%PDF-1.4 teste")

        # Rascunho é privado: outro usuário não baixa o anexo.
        self.client.force_login(self.outro_solicitante)
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 403)

    def test_qualquer_usuario_baixa_anexo_de_solicitacao_enviada(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)
        self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )
        services.enviar(solicitacao, self.solicitante)
        anexo = solicitacao.anexos.get()
        self.client.force_login(self.outro_solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:anexo_baixar", args=[solicitacao.pk, anexo.pk])
        )
        self.assertEqual(resposta.status_code, 200)

    def test_criador_exclui_anexo_do_rascunho(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )
        anexo = solicitacao.anexos.get()
        caminho = anexo.arquivo.path
        resposta = self.client.post(
            reverse("solicitacoes:anexo_excluir", args=[solicitacao.pk, anexo.pk])
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(solicitacao.anexos.count(), 0)
        import os

        self.assertFalse(os.path.exists(caminho))

    def test_secao_anexos_no_detalhe(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )
        resposta = self.client.get(
            reverse("solicitacoes:detalhe", args=[solicitacao.pk])
        )
        self.assertContains(resposta, "Anexos")
        self.assertContains(resposta, "oficio.pdf")
        self.assertContains(resposta, "Anexar arquivo")
