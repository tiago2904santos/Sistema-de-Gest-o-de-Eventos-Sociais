import re
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
    Municipio,
    OrgaoResponsavel,
    Regiao,
    Servico,
    TipoEvento,
    UnidadeMovel,
)
from viagens_cadastros.models import Cargo, Servidor

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
        cls.tipo_parana_em_acao = TipoEvento.objects.get_or_create(nome="Paraná em Ação")[0]
        cls.orgao = OrgaoResponsavel.objects.create(nome="Órgão Teste")
        cls.servico = Servico.objects.create(nome="Emissão de CIN")
        cls.outro_servico = Servico.objects.create(nome="Coleta de digitais")
        cls.equipe = Equipe.objects.create(nome="Equipe Alfa")
        cls.outra_equipe = Equipe.objects.create(nome="IIPR")
        # Motorista é papel, não cadastro: o servidor precisa do cargo para
        # figurar no select da solicitação.
        cargo_motorista = Cargo.objects.create(nome="MOTORISTA")
        cls.motorista = Servidor.objects.create(
            nome="Motorista Teste", cargo=cargo_motorista
        )
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

    def efetivar(self, funcao, *args, **kwargs):
        """Roda a ação e o que ela deixou para depois do commit (a viagem)."""
        with self.captureOnCommitCallbacks(execute=True):
            return funcao(*args, **kwargs)

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
        self.assertIn(
            {"campo": "Servidores — Equipe Alfa", "antes": "5", "depois": "3"},
            registro.alteracoes,
        )
        # A equipe aceita sem mudança não entra no registro.
        self.assertNotIn("IIPR", str(registro.alteracoes))

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
            solicitacao, self.solicitante, "Chuva forte no dia do evento."
        )

        self.assertEqual(solicitacao.status, StatusSolicitacao.CANCELADA)
        registro = solicitacao.historico.get(acao=AcaoHistorico.CANCELAMENTO)
        self.assertEqual(registro.observacao, "Chuva forte no dia do evento.")
        self.assertEqual(registro.usuario, self.solicitante)

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
        # O dossiê devolvido continua privado do criador e não pode ser excluído.
        self.assertFalse(perms.pode_ver(self.outro_solicitante, solicitacao))
        self.assertFalse(perms.pode_excluir(self.solicitante, solicitacao))

    def test_timeline_devolvida_reabre_primeira_etapa(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.devolver(solicitacao, self.gestor, "Ajustar equipe.")
        etapas = services.montar_timeline(solicitacao)
        self.assertEqual(etapas[0]["estado"], "atual")
        self.assertIn("correção", etapas[0]["subtitulo"])

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
            resposta, reverse("solicitacoes:editar", args=[solicitacao.pk])
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
        """As equipes ficam com os serviços; os anexos, no próprio cartão."""
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:nova"))
        self.assertContains(resposta, "Serviços e estrutura")
        self.assertContains(resposta, "Anexos")
        self.assertContains(resposta, 'name="equipes"')

    def test_criar_e_enviar_para_dg(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:nova"), self.dados_completos_post()
        )
        solicitacao = SolicitacaoEvento.objects.latest("pk")
        self.assertRedirects(
            resposta, reverse("solicitacoes:editar", args=[solicitacao.pk])
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
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)

    def test_dados_travam_apos_envio(self):
        """Tela única: depois do envio ela abre, mas só em leitura."""
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["somente_leitura"])
        self.assertTrue(resposta.context["dados_desabilitado"])
        self.assertNotContains(resposta, "Salvar alterações")
        # O POST continua barrado: leitura não vira edição.
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
            reverse("solicitacoes:editar", args=[solicitacao.pk])
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
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertContains(resposta, ">Despacho da DG<", html=False)

    def test_transicoes_exigem_post(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:enviar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 405)

    def test_enviar_pela_tela_do_registro(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:enviar", args=[solicitacao.pk])
        )
        self.assertRedirects(
            resposta, reverse("solicitacoes:editar", args=[solicitacao.pk])
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
        self.assertContains(resposta, "<b>Continuar</b>", html=False)

        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"fila": "rascunhos"}
        )
        self.assertEqual(resposta.context["pagina"].paginator.count, 1)

        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("solicitacoes:lista"))
        self.assertContains(resposta, "Aguardando despacho")
        self.assertContains(resposta, "<b>Despachar</b>", html=False)
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

        # O criador reenvia pela própria tela do registro (o formulário).
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
        self.assertContains(resposta, "<b>Continuar</b>", html=False)

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
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertContains(resposta, f'name="quantidade_dg_{self.equipe.pk}"')
        self.assertContains(resposta, str(self.equipe))

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
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertContains(resposta, "Salvar servidores")
        # A quantidade é editada na própria linha da equipe, pelo form do despacho.
        self.assertContains(
            resposta, f'name="quantidade_dg_{self.equipe.pk}" form="form-despacho"'
        )

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
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertContains(resposta, "Marcar como atendida")
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

    def test_usuario_nao_cancela_evento_de_terceiro_via_view(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.outro_solicitante)

        resposta = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)
        resposta = self.client.post(
            reverse("solicitacoes:cancelar_evento", args=[solicitacao.pk]),
            {"motivo_cancelamento": "Tentativa sem autorização."},
        )
        self.assertEqual(resposta.status_code, 403)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)

    def test_criador_cancela_proprio_evento_via_view(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)
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
        self.assertContains(resposta, "Deferidas")
        self.assertContains(resposta, "<b>Marcar como atendida</b>", html=False)

    def test_pagina_do_dg_traz_o_despacho_na_tela_do_registro(self):
        """A DG despacha na mesma tela do registro, com os dados travados."""
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)

        # Gestor com despacho pendente: dados em leitura + seção do despacho.
        self.client.force_login(self.gestor)
        resposta = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertContains(resposta, ">Despacho da DG<", html=False)
        self.assertTrue(resposta.context["somente_leitura"])
        self.assertTrue(resposta.context["dados_desabilitado"])
        self.assertContains(resposta, solicitacao.solicitante_nome)
        # As quantidades continuam editáveis no despacho.
        self.assertContains(resposta, f'name="quantidade_dg_{self.equipe.pk}"')

        # O solicitante abre a mesma tela, sem o formulário de despacho.
        self.client.force_login(self.solicitante)
        resposta = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertNotContains(resposta, ">Despacho da DG<", html=False)
        self.assertNotContains(resposta, f'name="quantidade_dg_{self.equipe.pk}"')

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
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 200)

    def test_registro_tem_uma_tela_so_o_formulario(self):
        """O registro não tem tela de resumo: abrir é abrir o formulário.

        Os dados ficam editáveis nos próprios campos e o acompanhamento, o
        histórico e as ações de workflow viram seções do mesmo fluxo.
        """
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)

        resposta = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )

        self.assertTemplateUsed(resposta, "pages/solicitacoes/form.html")
        self.assertFalse(resposta.context["somente_leitura"])
        # Os dados aparecem como campos do formulário, não como rótulo/valor.
        self.assertContains(resposta, 'name="solicitante_nome"')
        self.assertContains(resposta, 'name="municipio"')
        self.assertContains(resposta, solicitacao.solicitante_nome)
        # Seções migradas do antigo detalhe continuam na mesma tela.
        self.assertContains(resposta, 'aria-label="Acompanhamento da solicitação"', html=False)
        self.assertContains(resposta, "Histórico</h2>", html=False)
        self.assertContains(resposta, "Salvar rascunho")
        self.assertContains(resposta, "Enviar para a DG")

    def test_formularios_de_workflow_nao_ficam_aninhados(self):
        """Despacho, encerramento e anexos ficam fora do <form> principal."""
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)

        for usuario in [self.solicitante, self.gestor]:
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                resposta = self.client.get(
                    reverse("solicitacoes:editar", args=[solicitacao.pk])
                )
                html = resposta.content.decode()
                profundidade = maxima = 0
                for tag in re.findall(r"</?form\b", html):
                    profundidade += 1 if tag == "<form" else -1
                    maxima = max(maxima, profundidade)
                self.assertEqual(maxima, 1, "há <form> aninhado na tela")
                self.assertEqual(profundidade, 0, "há <form> sem fechamento")

    def test_tela_do_registro_nao_tem_lateral_flutuante(self):
        """Coluna única: nada de aside, sticky ou ações flutuantes."""
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)

        for url in [
            reverse("solicitacoes:nova"),
            reverse("solicitacoes:editar", args=[solicitacao.pk]),
            reverse("solicitacoes:lista"),
        ]:
            with self.subTest(url=url):
                resposta = self.client.get(url)
                conteudo = resposta.content.decode()
                self.assertNotIn("<aside", conteudo)
                self.assertNotIn('class="sticky', conteudo)
                self.assertNotIn("frm-lateral", conteudo)
                self.assertNotIn("frm-acoes--flut", conteudo)
                self.assertNotIn("frm-grade", conteudo)

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
        self.assertNotIn(enviada.pk, pks)
        self.assertNotIn(rascunho.pk, pks)

        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("solicitacoes:lista"))
        pks = [linha["solicitacao"].pk for linha in resposta.context["linhas"]]
        self.assertIn(enviada.pk, pks)

    def test_listagem_ordena_pela_coluna_pedida(self):
        primeira = self.criar_solicitacao(solicitante_nome="Ana")
        segunda = self.criar_solicitacao(solicitante_nome="Zulmira")
        self.client.force_login(self.solicitante)

        crescente = self.client.get(
            reverse("solicitacoes:lista"), {"ordem": "solicitante"}
        )
        decrescente = self.client.get(
            reverse("solicitacoes:lista"), {"ordem": "-solicitante"}
        )

        def nomes(resposta):
            return [
                linha["solicitacao"].solicitante_nome
                for linha in resposta.context["linhas"]
            ]

        self.assertLess(
            nomes(crescente).index(primeira.solicitante_nome),
            nomes(crescente).index(segunda.solicitante_nome),
        )
        self.assertGreater(
            nomes(decrescente).index(primeira.solicitante_nome),
            nomes(decrescente).index(segunda.solicitante_nome),
        )

    def test_ordem_invalida_cai_no_padrao(self):
        self.criar_solicitacao()
        self.client.force_login(self.solicitante)

        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"ordem": "'; DROP TABLE"}
        )

        self.assertEqual(resposta.status_code, 200)

    def test_devolvida_mostra_motivo_em_destaque(self):
        """O motivo do ajuste não pode ficar só numa célula do histórico."""
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.devolver(solicitacao, self.gestor, observacao="Detalhe o local.")
        self.client.force_login(self.solicitante)

        resposta = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )

        self.assertContains(resposta, "Enviada para correção pela Diretoria-Geral")
        self.assertContains(resposta, "Detalhe o local.")
        # Tela única: o usuário já está no formulário e reenvia daqui mesmo.
        self.assertFalse(resposta.context["somente_leitura"])
        self.assertContains(resposta, "Enviar para a DG")

    def test_despacho_invalido_preserva_a_decisao_escolhida(self):
        """Errar a observação não pode apagar a decisão já selecionada."""
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.gestor)

        resposta = self.client.post(
            reverse("solicitacoes:despachar", args=[solicitacao.pk]),
            {"decisao": DespachoForm.DEVOLVER, "observacao": ""},
        )

        self.assertTrue(resposta["Location"].endswith("#despacho-dg"))
        detalhe = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertEqual(
            detalhe.context["despacho_pendente"]["decisao"], DespachoForm.DEVOLVER
        )


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
            resposta, reverse("solicitacoes:editar", args=[solicitacao.pk])
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
        self.assertContains(resposta, 'name="anexos"')
        self.assertContains(resposta, "Arraste arquivos aqui ou clique para selecionar")
        self.assertContains(resposta, 'enctype="multipart/form-data"')
        self.assertTemplateUsed(resposta, "components/upload_anexos.html")
        self.assertContains(resposta, 'data-upload-dropzone', count=1)

    def test_edicao_anexa_pelo_modal(self):
        """Na edição, anexar abre o modal: o cartão fica só com a lista."""
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        url = reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk])
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertContains(resposta, f'href="{url}" data-cadastro-modal')
        self.assertNotContains(resposta, "data-upload-dropzone")
        # O trecho do modal vem pelo mesmo endereço, com o cabeçalho dos cadastros.
        modal = self.client.get(url, HTTP_X_CADASTRO_MODAL="1")
        self.assertTemplateUsed(modal, "components/upload_anexos.html")
        self.assertContains(modal, "data-upload-dropzone", count=1)
        self.assertContains(modal, "data-cadastro-form")
        self.assertNotContains(modal, "data-anexo-enviar-ao-selecionar")

    def test_anexo_pelo_modal_responde_json(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
            HTTP_X_CADASTRO_MODAL="1",
        )
        self.assertEqual(resposta.json(), {"ok": True})
        self.assertEqual(solicitacao.anexos.count(), 1)

    def test_criador_anexa_no_rascunho(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )
        self.assertRedirects(
            resposta, reverse("solicitacoes:editar", args=[solicitacao.pk])
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

    def test_anexo_bloqueado_apos_finalizacao_mesmo_para_superusuario(self):
        """Dossiê de evento encerrado não muda mais — nem por superusuário."""
        solicitacao = self.solicitacao_completa()
        solicitacao.status = StatusSolicitacao.ATENDIDA
        solicitacao.save(update_fields=["status"])
        superusuario = get_user_model().objects.create_superuser(
            "raiz-anexos", password="x"
        )
        self.client.force_login(superusuario)

        resposta = self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )

        self.assertEqual(resposta.status_code, 403)
        detalhe = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertNotContains(detalhe, "Anexar arquivo")
        self.assertNotContains(detalhe, "data-upload-anexos")

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

    def test_usuario_nao_baixa_anexo_de_solicitacao_enviada_de_terceiro(self):
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
        self.assertEqual(resposta.status_code, 403)

    def test_conteudo_disfarcado_de_pdf_e_rejeitado(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": SimpleUploadedFile("oficio.pdf", b"MZ executavel")},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(solicitacao.anexos.exists())

    def test_criador_exclui_anexo_do_rascunho(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )
        anexo = solicitacao.anexos.get()
        caminho = anexo.arquivo.path
        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.post(
                reverse("solicitacoes:anexo_excluir", args=[solicitacao.pk, anexo.pk])
            )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(solicitacao.anexos.count(), 0)
        import os

        self.assertFalse(os.path.exists(caminho))

    def test_excluir_rascunho_apaga_os_arquivos_dos_anexos(self):
        """"Remove o rascunho e os anexos dele": o arquivo sai do servidor também."""
        import os

        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        for nome in ("oficio.pdf", "foto.pdf"):
            self.client.post(
                reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
                {"arquivo": self.arquivo(nome)},
            )
        caminhos = [anexo.arquivo.path for anexo in solicitacao.anexos.all()]
        self.assertEqual(len(caminhos), 2)
        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.post(
                reverse("solicitacoes:excluir", args=[solicitacao.pk])
            )
        self.assertEqual(resposta.status_code, 302)
        for caminho in caminhos:
            self.assertFalse(os.path.exists(caminho))

    def test_limpeza_de_orfaos_cobre_a_pasta_das_solicitacoes(self):
        from io import StringIO

        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        from django.core.management import call_command

        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )
        vivo = solicitacao.anexos.get().arquivo.name
        orfao = default_storage.save("solicitacoes/999/sobra.pdf", ContentFile(b"%PDF-1.4"))
        saida = StringIO()
        call_command("limpar_arquivos_orfaos", "--apagar", stdout=saida)
        self.assertIn(f"Arquivo órfão: {orfao}", saida.getvalue())
        self.assertFalse(default_storage.exists(orfao))
        self.assertTrue(default_storage.exists(vivo))

    def test_secao_anexos_na_tela_do_registro(self):
        """Os anexos do registro vivem na seção do próprio formulário."""
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        self.client.post(
            reverse("solicitacoes:anexo_adicionar", args=[solicitacao.pk]),
            {"arquivo": self.arquivo()},
        )
        resposta = self.client.get(
            reverse("solicitacoes:editar", args=[solicitacao.pk])
        )
        self.assertContains(resposta, "Anexos")
        self.assertContains(resposta, "oficio.pdf")
        self.assertContains(resposta, "Anexar arquivo")
        # A zona de arrastar mora no modal, não no cartão.
        self.assertNotContains(resposta, "Arraste arquivos aqui ou clique para selecionar")
        # Um envio explícito, para não competir com o salvamento do formulário.
        self.assertContains(resposta, "Anexar arquivo")
        self.assertNotContains(resposta, "data-anexo-enviar-ao-selecionar")
        # O envio acontece no modal, fora do <form> principal.
        self.assertNotContains(resposta, 'id="form-anexo-upload"')
        self.assertContains(resposta, "data-cadastro-dialog", count=1)


class GeracaoDeViagemPeloDespacho(BaseSolicitacaoTestCase):
    """O despacho da DG faz a viagem nascer — em rascunho, e só o que se sabe."""

    def _deferir(self, solicitacao):
        services.enviar(solicitacao, self.solicitante)
        return self.efetivar(services.despachar,
            solicitacao, self.gestor, DecisaoDG.ATENDER, observacao="Autorizado"
        )

    def test_deferir_cria_a_viagem_ligada_a_solicitacao(self):
        from solicitacoes import integracao_viagens as iv

        solicitacao = self.solicitacao_completa()
        self._deferir(solicitacao)

        viagem = iv.viagem_da_solicitacao(solicitacao)
        self.assertIsNotNone(viagem, "o despacho deveria ter gerado a viagem")
        self.assertEqual(viagem.destino_municipio, solicitacao.municipio)
        self.assertEqual(viagem.data_inicio, solicitacao.data_inicio_evento)
        self.assertEqual(viagem.data_fim, solicitacao.data_fim_evento)
        # A ligação existe no banco, não na memória de quem criou.
        self.assertEqual(viagem.roteiros.first().solicitacao_id, solicitacao.pk)

    def test_o_numero_da_solicitacao_fica_no_motivo(self):
        """Seis meses depois, é o fio que liga a viagem ao pedido que a causou."""
        from solicitacoes import integracao_viagens as iv

        solicitacao = self.solicitacao_completa()
        self._deferir(solicitacao)
        viagem = iv.viagem_da_solicitacao(solicitacao)
        self.assertIn(f"#{solicitacao.pk}", viagem.motivo)

    def test_as_equipes_autorizadas_ficam_registradas_no_roteiro(self):
        from solicitacoes import integracao_viagens as iv

        solicitacao = self.solicitacao_completa()
        self._deferir(solicitacao)
        roteiro = iv.viagem_da_solicitacao(solicitacao).roteiros.first()
        self.assertIn(str(self.equipe), roteiro.observacoes)
        self.assertIn(f"#{solicitacao.pk}", roteiro.observacoes)

    def test_equipe_sem_quantidade_aparece_mesmo_assim(self):
        """O fluxo novo exige a quantidade para enviar; o histórico não tinha.

        Das 101 solicitações reais, 98 têm equipe e só 6 têm o número — elas
        vieram da importação do legado, antes da validação existir. Filtrar
        pela quantidade esconderia de que setor chamar a equipe justamente
        nesses casos, que são a maioria do que está no banco.
        """
        from solicitacoes import integracao_viagens as iv

        solicitacao = self.criar_solicitacao()
        solicitacao.itens_equipe.create(equipe=self.equipe)  # como o legado importou

        resumo = iv.resumo_das_equipes(solicitacao)
        self.assertIn(str(self.equipe), resumo)
        self.assertIn("sem quantidade", resumo)

    def test_nao_atender_nao_cria_viagem(self):
        from solicitacoes import integracao_viagens as iv

        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.efetivar(services.despachar,
            solicitacao, self.gestor, DecisaoDG.NAO_ATENDER, observacao="Sem efetivo"
        )
        self.assertIsNone(iv.viagem_da_solicitacao(solicitacao))

    def test_nao_gera_viagem_duas_vezes(self):
        from solicitacoes import integracao_viagens as iv
        from viagens_viagem.models import Viagem

        solicitacao = self.solicitacao_completa()
        self._deferir(solicitacao)
        antes = Viagem.objects.count()

        cabe, motivo = iv.pode_gerar(solicitacao)
        self.assertFalse(cabe)
        self.assertIn("já tem viagem", motivo)
        with self.assertRaises(ValueError):
            iv.gerar_viagem(solicitacao, self.gestor)
        self.assertEqual(Viagem.objects.count(), antes)

    def test_falha_ao_gerar_viagem_nao_derruba_o_despacho(self):
        """A decisão da DG é o ato administrativo; a viagem é consequência.

        Perder um despacho porque o módulo vizinho falhou seria inaceitável —
        então a geração engole o próprio erro e registra no log.
        """
        from unittest.mock import patch

        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        with patch(
            "solicitacoes.integracao_viagens.gerar_viagem",
            side_effect=RuntimeError("banco fora do ar"),
        ):
            self.efetivar(services.despachar,
                solicitacao, self.gestor, DecisaoDG.ATENDER, observacao="Autorizado"
            )

        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.DEFERIDA_EM_ANDAMENTO)
        self.assertEqual(solicitacao.decisao_dg, DecisaoDG.ATENDER)

    def test_o_que_falta_lista_o_que_a_solicitacao_nao_sabia(self):
        """Quem vai, com que viatura e com que motorista decide a diária."""
        from solicitacoes import integracao_viagens as iv

        solicitacao = self.solicitacao_completa()
        self._deferir(solicitacao)
        faltando = iv.o_que_falta(iv.viagem_da_solicitacao(solicitacao))

        self.assertIn("Município de onde a equipe sai", faltando)
        self.assertTrue(any("Ofício" in item for item in faltando))


class RedespachoAposAlteracaoTests(BaseSolicitacaoTestCase):
    """Mexer depois do despacho devolve o pedido à DG antes do atendimento."""

    def setUp(self):
        from . import permissions

        self.perms = permissions

    def _deferida(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        return solicitacao

    def test_alteracao_volta_para_despacho_e_bloqueia_atendimento(self):
        solicitacao = self._deferida()
        self.assertTrue(self.perms.pode_concluir(self.solicitante, solicitacao))
        services.reenviar_apos_edicao(
            solicitacao,
            self.solicitante,
            [{"campo": "Local do evento", "antes": "A", "depois": "B"}],
        )
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        self.assertEqual(solicitacao.decisao_dg, DecisaoDG.PENDENTE)
        self.assertIsNone(solicitacao.decidido_em)
        # Sem despacho novo, ninguém marca como atendida.
        self.assertFalse(self.perms.pode_concluir(self.solicitante, solicitacao))
        self.assertTrue(self.perms.pode_despachar(self.gestor, solicitacao))
        registro = solicitacao.historico.last()
        self.assertEqual(registro.acao, AcaoHistorico.REENVIO)
        self.assertIn("novo despacho", registro.observacao)

    def test_rascunho_nao_se_reabre(self):
        solicitacao = self.solicitacao_completa()
        self.assertFalse(self.perms.pode_reabrir(self.solicitante, solicitacao))
        with self.assertRaises(services.TransicaoInvalida):
            services.reenviar_apos_edicao(solicitacao, self.solicitante, [])

    def test_enviada_fica_travada_ate_para_o_superusuario(self):
        solicitacao = self._deferida()
        self.assertFalse(self.perms.pode_editar_dados(self.superusuario, solicitacao))
        self.client.force_login(self.solicitante)
        dados = self.dados_completos_post(acao="rascunho")
        dados["local_evento"] = "Outro local"
        resposta = self.client.post(
            reverse("solicitacoes:editar", args=[solicitacao.pk]), dados
        )
        self.assertEqual(resposta.status_code, 403)
        # A tela mostra o botão Editar, não o de salvar.
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertContains(resposta, "?reabrir=1")
        self.assertNotContains(resposta, "Salvar alterações")

    def test_editar_pela_tela_devolve_para_a_dg_com_o_que_mudou(self):
        solicitacao = self._deferida()
        self.client.force_login(self.solicitante)
        url = reverse("solicitacoes:editar", args=[solicitacao.pk])
        resposta = self.client.get(url + "?reabrir=1")
        self.assertContains(resposta, "Salvar e reenviar para a DG")
        dados = self.dados_completos_post(acao="rascunho")
        dados["reabrir"] = "1"
        dados["local_evento"] = "Outro local"
        dados[f"quantidade_equipe_{self.equipe.pk}"] = 5
        resposta = self.client.post(url, dados, follow=True)
        self.assertEqual(resposta.status_code, 200)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.AGUARDANDO_DESPACHO)
        registro = solicitacao.historico.last()
        self.assertEqual(registro.acao, AcaoHistorico.REENVIO)
        self.assertIn(
            {"campo": "Local do evento", "antes": "Praça central", "depois": "Outro local"},
            registro.alteracoes,
        )
        self.assertContains(resposta, "Outro local")

    def test_editar_sem_mudar_nada_nao_reenvia(self):
        solicitacao = self._deferida()
        self.client.force_login(self.solicitante)
        dados = self.dados_completos_post(acao="rascunho")
        dados["reabrir"] = "1"
        dados[f"quantidade_equipe_{self.equipe.pk}"] = 5
        dados.pop("unidade_movel")
        dados.pop("unidade_movel_designada")
        self.client.post(reverse("solicitacoes:editar", args=[solicitacao.pk]), dados)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, StatusSolicitacao.DEFERIDA_EM_ANDAMENTO)

    def test_atendida_so_depois_do_evento(self):
        from datetime import timedelta

        from django.utils import timezone

        hoje = timezone.localdate()
        solicitacao = self.criar_solicitacao(
            data_inicio_evento=hoje, data_fim_evento=hoje + timedelta(days=1)
        )
        solicitacao.itens_servico.create(servico=self.servico)
        solicitacao.itens_equipe.create(equipe=self.equipe, quantidade_servidores=5)
        services.enviar(solicitacao, self.solicitante)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        self.assertFalse(self.perms.pode_concluir(self.solicitante, solicitacao))
        with self.assertRaises(ValidationError):
            services.concluir_atendimento(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertContains(resposta, "Atendida só após")


class ViagemAcompanhaSolicitacaoTests(BaseSolicitacaoTestCase):
    """Depois de gerada, a viagem segue a solicitação: muda, cancela ou avisa."""

    def _deferida_com_viagem(self):
        from solicitacoes import integracao_viagens as iv

        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.efetivar(services.despachar, solicitacao, self.gestor, DecisaoDG.ATENDER, observacao="Ok")
        viagem = iv.viagem_da_solicitacao(solicitacao)
        self.assertIsNotNone(viagem)
        return solicitacao, viagem

    def _operador_viagens(self):
        operador = User.objects.create_user("operador-vg", password="x")
        operador.groups.add(Group.objects.get_or_create(name="VIAGENS_OPERADOR")[0])
        return operador

    def test_roteiro_nasce_do_tipo_solicitacao_de_evento(self):
        from viagens_roteiros.models import Roteiro

        _solicitacao, viagem = self._deferida_com_viagem()
        self.assertEqual(viagem.roteiros.get().tipo, Roteiro.Tipo.EVENTO)

    def test_cancelar_evento_cancela_a_viagem_sem_documentos(self):
        solicitacao, viagem = self._deferida_com_viagem()
        self.efetivar(services.cancelar_evento, solicitacao, self.solicitante, "Chuva forte")
        viagem.refresh_from_db()
        self.assertTrue(viagem.cancelado)
        self.assertIn(f"Solicitação #{solicitacao.pk}", viagem.motivo_cancelamento)
        self.assertIn("Chuva forte", viagem.motivo_cancelamento)
        # O roteiro vai junto, em cascata.
        self.assertTrue(viagem.roteiros.get().cancelado)

    def test_nao_atender_no_novo_despacho_cancela_a_viagem(self):
        solicitacao, viagem = self._deferida_com_viagem()
        services.reenviar_apos_edicao(
            solicitacao, self.solicitante,
            [{"campo": "Local do evento", "antes": "A", "depois": "B"}],
        )
        self.efetivar(services.despachar,
            solicitacao, self.gestor, DecisaoDG.NAO_ATENDER, observacao="Sem efetivo"
        )
        viagem.refresh_from_db()
        self.assertTrue(viagem.cancelado)

    def test_com_documento_emitido_avisa_o_operador_em_vez_de_cancelar(self):
        from core.models import Notificacao
        from viagens_oficios.models import Oficio

        operador = self._operador_viagens()
        solicitacao, viagem = self._deferida_com_viagem()
        Oficio.objects.create(motivo="Da viagem", viagem=viagem)
        self.efetivar(services.cancelar_evento, solicitacao, self.solicitante, "Evento adiado")
        viagem.refresh_from_db()
        self.assertFalse(viagem.cancelado)
        aviso = Notificacao.objects.get(usuario=operador)
        self.assertIn(f"Viagem #{viagem.pk}", aviso.titulo)
        self.assertIn(reverse("viagens_viagem:painel", args=[viagem.pk]), aviso.link)

    def test_novo_deferimento_atualiza_a_viagem(self):
        novo_municipio = Municipio.objects.create(
            nome="Outra Cidade", estado=self.estado, regiao=self.regiao
        )
        solicitacao, viagem = self._deferida_com_viagem()
        solicitacao.local_evento = "Ginásio municipal"
        solicitacao.municipio = novo_municipio
        solicitacao.data_inicio_evento = date(2026, 9, 20)
        solicitacao.data_fim_evento = date(2026, 9, 21)
        solicitacao.save()
        services.reenviar_apos_edicao(
            solicitacao, self.solicitante,
            [{"campo": "Local do evento", "antes": "Praça central", "depois": "Ginásio municipal"}],
        )
        self.efetivar(services.despachar, solicitacao, self.gestor, DecisaoDG.ATENDER, observacao="Ok")
        viagem.refresh_from_db()
        self.assertEqual(viagem.destino_municipio, novo_municipio)
        self.assertEqual(viagem.data_inicio, date(2026, 9, 20))
        self.assertEqual(viagem.data_fim, date(2026, 9, 21))
        self.assertIn("Ginásio municipal", viagem.motivo)
        roteiro = viagem.roteiros.get()
        self.assertIn("Ginásio municipal", roteiro.observacoes)
        self.assertEqual(roteiro.destinos.get().municipio, novo_municipio)

    def test_novo_deferimento_com_documento_nao_mexe_e_avisa(self):
        from core.models import Notificacao
        from viagens_oficios.models import Oficio

        operador = self._operador_viagens()
        solicitacao, viagem = self._deferida_com_viagem()
        Oficio.objects.create(motivo="Da viagem", viagem=viagem)
        solicitacao.local_evento = "Ginásio municipal"
        solicitacao.save()
        services.reenviar_apos_edicao(
            solicitacao, self.solicitante,
            [{"campo": "Local do evento", "antes": "Praça central", "depois": "Ginásio municipal"}],
        )
        self.efetivar(services.despachar, solicitacao, self.gestor, DecisaoDG.ATENDER)
        viagem.refresh_from_db()
        self.assertNotIn("Ginásio municipal", viagem.motivo)
        self.assertTrue(Notificacao.objects.filter(usuario=operador).exists())

    def test_painel_mostra_viagem_desatualizada_com_o_que_mudou(self):
        solicitacao, viagem = self._deferida_com_viagem()
        services.reenviar_apos_edicao(
            solicitacao, self.solicitante,
            [{"campo": "Local do evento", "antes": "Praça central", "depois": "Ginásio municipal"}],
        )
        self.client.force_login(self.superusuario)
        resposta = self.client.get(reverse("viagens_viagem:etapa", args=[viagem.pk, 1]))
        self.assertContains(resposta, "Viagem desatualizada")
        self.assertContains(resposta, "Ginásio municipal")
        self.assertContains(resposta, reverse("solicitacoes:editar", args=[solicitacao.pk]))

    def test_painel_mostra_de_qual_solicitacao_veio(self):
        solicitacao, viagem = self._deferida_com_viagem()
        self.client.force_login(self.superusuario)
        resposta = self.client.get(reverse("viagens_viagem:etapa", args=[viagem.pk, 1]))
        self.assertContains(resposta, f"Solicitação de evento #{solicitacao.pk}")
        self.assertNotContains(resposta, "Viagem desatualizada")


class ViagemNaTelaDaSolicitacaoTests(BaseSolicitacaoTestCase):
    """O cartão "Viagem" na solicitação e o "Gerar viagem" pela tela."""

    def _deferida_sem_viagem(self):
        # Sem efetivar: o on_commit não roda e a viagem não nasce, como nas
        # deferidas antes da geração automática.
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)
        return solicitacao

    def test_viagem_so_nasce_depois_do_commit(self):
        from solicitacoes import integracao_viagens as iv

        solicitacao = self._deferida_sem_viagem()
        self.assertIsNone(iv.viagem_da_solicitacao(solicitacao))

    def test_falha_na_viagem_avisa_quem_despachou(self):
        from unittest.mock import patch

        from core.models import Notificacao

        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        with patch(
            "solicitacoes.integracao_viagens.gerar_viagem",
            side_effect=RuntimeError("falhou"),
        ):
            self.efetivar(services.despachar, solicitacao, self.gestor, DecisaoDG.ATENDER)
        self.assertTrue(
            Notificacao.objects.filter(
                usuario=self.gestor, titulo__contains="viagem não foi atualizada"
            ).exists()
        )

    def test_cartao_mostra_gerar_viagem_para_a_dg(self):
        solicitacao = self._deferida_sem_viagem()
        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertContains(resposta, 'id="viagem"')
        self.assertContains(resposta, reverse("solicitacoes:gerar_viagem", args=[solicitacao.pk]))

    def test_solicitante_ve_o_cartao_sem_o_botao(self):
        solicitacao = self._deferida_sem_viagem()
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertContains(resposta, 'id="viagem"')
        self.assertNotContains(resposta, reverse("solicitacoes:gerar_viagem", args=[solicitacao.pk]))

    def test_rascunho_nao_tem_cartao(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertNotContains(resposta, 'id="viagem"')

    def test_gerar_viagem_pela_tela(self):
        from solicitacoes import integracao_viagens as iv

        solicitacao = self._deferida_sem_viagem()
        self.client.force_login(self.gestor)
        resposta = self.client.post(
            reverse("solicitacoes:gerar_viagem", args=[solicitacao.pk]), follow=True
        )
        viagem = iv.viagem_da_solicitacao(solicitacao)
        self.assertIsNotNone(viagem)
        # O cartão passa a mostrar a viagem e o que falta completar.
        self.assertContains(resposta, f"Viagem #{viagem.pk}")
        self.assertContains(resposta, "Município de onde a equipe sai")

    def test_gerar_viagem_de_novo_mostra_o_motivo(self):
        solicitacao = self._deferida_sem_viagem()
        self.client.force_login(self.gestor)
        url = reverse("solicitacoes:gerar_viagem", args=[solicitacao.pk])
        self.client.post(url)
        resposta = self.client.post(url, follow=True)
        self.assertContains(resposta, "já tem viagem gerada")

    def test_solicitante_nao_gera_viagem(self):
        solicitacao = self._deferida_sem_viagem()
        self.client.force_login(self.solicitante)
        resposta = self.client.post(reverse("solicitacoes:gerar_viagem", args=[solicitacao.pk]))
        self.assertEqual(resposta.status_code, 403)

    def test_operador_de_viagens_gera_e_vai_para_a_viagem(self):
        from solicitacoes import integracao_viagens as iv

        operador = User.objects.create_user("operador", password="x")
        operador.groups.add(Group.objects.get_or_create(name="VIAGENS_OPERADOR")[0])
        solicitacao = self._deferida_sem_viagem()
        self.client.force_login(operador)
        resposta = self.client.post(reverse("solicitacoes:gerar_viagem", args=[solicitacao.pk]))
        viagem = iv.viagem_da_solicitacao(solicitacao)
        self.assertRedirects(
            resposta, reverse("viagens_viagem:painel", args=[viagem.pk]),
            fetch_redirect_response=False,
        )


class TimelineComORegistroMaisRecenteTests(BaseSolicitacaoTestCase):
    """A barra de etapas mostra o envio e a decisão que valem, não os primeiros."""

    def _datar(self, solicitacao):
        """Espaça o histórico em horas cheias, na ordem em que foi gravado."""
        from datetime import datetime, timedelta

        from django.utils import timezone

        inicio = timezone.make_aware(datetime(2026, 8, 1, 9, 0))
        for i, registro in enumerate(solicitacao.historico.order_by("pk")):
            type(registro).objects.filter(pk=registro.pk).update(
                criado_em=inicio + timedelta(hours=i)
            )

    def test_reenvio_e_novo_despacho(self):
        solicitacao = self.solicitacao_completa()
        services.registrar_historico(solicitacao, self.solicitante, AcaoHistorico.CRIACAO)
        services.enviar(solicitacao, self.solicitante)                      # 10:00
        services.despachar(solicitacao, self.gestor, DecisaoDG.ATENDER)     # 11:00
        services.reenviar_apos_edicao(                                      # 12:00
            solicitacao, self.solicitante,
            [{"campo": "Local do evento", "antes": "A", "depois": "B"}],
        )
        services.despachar(solicitacao, self.superusuario, DecisaoDG.ATENDER)  # 13:00
        self._datar(solicitacao)
        solicitacao = SolicitacaoEvento.objects.prefetch_related("historico__usuario").get(
            pk=solicitacao.pk
        )
        envio, _aguardando, deferida, _final = services.montar_timeline(solicitacao)
        self.assertEqual(envio["quando"], "01/08/2026 12:00")
        self.assertEqual(deferida["quando"], "01/08/2026 13:00")
        self.assertEqual(deferida["usuario"], str(self.superusuario))

    def test_envio_prefere_o_envio_a_criacao(self):
        solicitacao = self.solicitacao_completa()
        services.registrar_historico(solicitacao, self.solicitante, AcaoHistorico.CRIACAO)
        services.enviar(solicitacao, self.solicitante)
        self._datar(solicitacao)
        solicitacao.refresh_from_db()
        envio = services.montar_timeline(solicitacao)[0]
        self.assertEqual(envio["quando"], "01/08/2026 10:00")


@override_settings(EPROTOCOLO={"AMBIENTE": "mock"})
class ProtocoloDaSolicitacaoTests(BaseSolicitacaoTestCase):
    """Número do eProtocolo guardado, buscável e com a consulta do andamento."""

    def test_formulario_normaliza_o_numero(self):
        self.client.force_login(self.solicitante)
        dados = self.dados_completos_post(acao="rascunho")
        dados["protocolo"] = "123456789"
        self.client.post(reverse("solicitacoes:nova"), dados)
        solicitacao = SolicitacaoEvento.objects.get()
        self.assertEqual(solicitacao.protocolo, "12.345.678-9")

    def test_numero_com_digitos_errados_e_recusado(self):
        form = SolicitacaoForm(data={**self.dados_completos_post(acao="rascunho"), "protocolo": "1234"})
        self.assertFalse(form.is_valid())
        self.assertIn("protocolo", form.errors)

    def test_busca_pelo_numero_com_ou_sem_pontos(self):
        alvo = self.criar_solicitacao(protocolo="12.345.678-9")
        self.criar_solicitacao(protocolo="98.765.432-1")
        self.client.force_login(self.solicitante)
        for termo in ("12.345.678-9", "123456789"):
            resposta = self.client.get(reverse("solicitacoes:lista"), {"q": termo})
            self.assertEqual(
                [s.pk for s in resposta.context["pagina"].object_list], [alvo.pk], termo
            )

    def test_consultar_andamento_mostra_o_cartao(self):
        solicitacao = self.criar_solicitacao(protocolo="12.345.678-9")
        self.client.force_login(self.solicitante)
        url = reverse("solicitacoes:editar", args=[solicitacao.pk])
        resposta = self.client.get(url)
        self.assertContains(resposta, "Consultar andamento")
        resposta = self.client.post(
            reverse("solicitacoes:consultar_protocolo", args=[solicitacao.pk]), follow=True
        )
        self.assertContains(resposta, "data-andamento-protocolo")
        self.assertContains(resposta, "Protocolo 12.345.678-9")
        self.assertContains(resposta, "simulado")
        # Lido uma vez: recarregar a tela não repete o cartão.
        self.assertNotContains(self.client.get(url), "data-andamento-protocolo")

    def test_sem_protocolo_nao_tem_botao(self):
        solicitacao = self.criar_solicitacao()
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertNotContains(resposta, "Consultar andamento")

    def test_falha_do_eprotocolo_vira_mensagem(self):
        from unittest.mock import patch

        from integracoes.eprotocolo.exceptions import EProtocoloUnavailableError

        solicitacao = self.criar_solicitacao(protocolo="12.345.678-9")
        self.client.force_login(self.solicitante)
        with patch(
            "integracoes.eprotocolo.services.consultar_protocolo",
            side_effect=EProtocoloUnavailableError(),
        ):
            resposta = self.client.post(
                reverse("solicitacoes:consultar_protocolo", args=[solicitacao.pk]),
                follow=True,
            )
        self.assertContains(resposta, "Não foi possível consultar o eProtocolo")
        self.assertNotContains(resposta, "data-andamento-protocolo")

    def test_quem_nao_ve_a_solicitacao_nao_consulta(self):
        solicitacao = self.criar_solicitacao(protocolo="12.345.678-9")
        self.client.force_login(self.outro_solicitante)
        resposta = self.client.post(
            reverse("solicitacoes:consultar_protocolo", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 403)


class EdicaoSimultaneaTests(BaseSolicitacaoTestCase):
    """Salvar a tela velha não desfaz o ajuste ou a decisão de outra pessoa."""

    def _versao_da_tela(self, url):
        resposta = self.client.get(url)
        versao = resposta.context["valores"]["versao"]
        self.assertContains(resposta, f'name="versao" value="{versao}"')
        return versao

    def test_ajuste_da_dg_no_meio_barra_o_salvar_do_solicitante(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.solicitante)
        url = reverse("solicitacoes:editar", args=[solicitacao.pk])
        versao = self._versao_da_tela(url + "?reabrir=1")
        self.assertTrue(versao)

        # Enquanto a tela está aberta, a DG ajusta os servidores.
        services.salvar_ajustes_dg(solicitacao, self.gestor, {self.equipe.pk: 9})

        dados = self.dados_completos_post(acao="rascunho")
        dados.update({"reabrir": "1", "versao": versao, "local_evento": "Outro local"})
        resposta = self.client.post(url, dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "alterada por outra pessoa")
        item = solicitacao.itens_equipe.get()
        self.assertEqual(item.quantidade_servidores, 9)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.local_evento, "Praça central")

    def test_versao_em_dia_salva_normalmente(self):
        solicitacao = self.solicitacao_completa()
        self.client.force_login(self.solicitante)
        url = reverse("solicitacoes:editar", args=[solicitacao.pk])
        dados = self.dados_completos_post(acao="rascunho")
        dados.update({"versao": self._versao_da_tela(url), "local_evento": "Ginásio"})
        resposta = self.client.post(url, dados)
        self.assertEqual(resposta.status_code, 302)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.local_evento, "Ginásio")

    def test_ajuste_da_dg_muda_a_versao(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        antes = SolicitacaoEvento.objects.get(pk=solicitacao.pk).atualizado_em
        services.salvar_ajustes_dg(solicitacao, self.gestor, {self.equipe.pk: 7})
        depois = SolicitacaoEvento.objects.get(pk=solicitacao.pk).atualizado_em
        self.assertGreater(depois, antes)


class ConsultasDaListaTests(BaseSolicitacaoTestCase):
    """O perfil do usuário é lido uma vez por requisição, não uma por linha."""

    def test_lista_da_dg_nao_consulta_grupos_por_linha(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for _ in range(15):
            self.criar_solicitacao(unidade_movel=True, unidade_movel_designada=self.van)
        self.client.force_login(self.gestor)
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(reverse("solicitacoes:lista"))
        self.assertEqual(resposta.status_code, 200)
        de_grupo = [c for c in consultas.captured_queries if '"auth_group"' in c["sql"]]
        self.assertLessEqual(len(de_grupo), 3)
        de_unidade = [
            c for c in consultas.captured_queries
            if 'FROM "cadastros_unidademovel"' in c["sql"]
        ]
        self.assertEqual(de_unidade, [])

    def test_cache_de_grupos_vale_para_o_objeto(self):
        from . import permissions

        usuario = User.objects.create_user("sem-grupo", password="x")
        self.assertFalse(permissions.eh_gestor_dg(usuario))
        with self.assertNumQueries(0):
            permissions.eh_gestor_dg(usuario)
            permissions.eh_administrador(usuario)


class FiltrosVisiveisDaListaTests(BaseSolicitacaoTestCase):
    """Filtro que veio do Dashboard aparece, sai com um "x" e não se soma às filas."""

    def setUp(self):
        from django.utils import timezone

        self.hoje = timezone.localdate()
        # Deferida deste ano, deferida de ano passado e uma aguardando despacho.
        self.deste_ano = self.criar_solicitacao(
            status=StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
            data_solicitacao=self.hoje,
        )
        self.antiga = self.criar_solicitacao(
            status=StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
            data_solicitacao=date(self.hoje.year - 1, 3, 1),
        )
        self.aguardando = self.criar_solicitacao(
            status=StatusSolicitacao.AGUARDANDO_DESPACHO,
            data_solicitacao=self.hoje,
        )
        self.client.force_login(self.gestor)

    def _ids(self, resposta):
        return {s.pk for s in resposta.context["pagina"].object_list}

    def test_fila_deferidas_no_ano_bate_com_o_cartao(self):
        resposta = self.client.get(reverse("solicitacoes:lista"), {"fila": "deferidas_ano"})
        self.assertEqual(self._ids(resposta), {self.deste_ano.pk})
        self.assertContains(resposta, "Deferidas no ano")
        self.assertContains(resposta, "data-filtro-ativo")
        # A fila é oculta: "Todas" não fica aceso.
        self.assertEqual(resposta.context["situacao_ativa"], "deferidas_ano")

    def test_fila_proximos_30_dias(self):
        from datetime import timedelta

        proxima = self.criar_solicitacao(
            status=StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
            data_inicio_evento=self.hoje + timedelta(days=5),
            data_fim_evento=self.hoje + timedelta(days=5),
        )
        self.criar_solicitacao(
            status=StatusSolicitacao.CANCELADA,
            data_inicio_evento=self.hoje + timedelta(days=5),
            data_fim_evento=self.hoje + timedelta(days=5),
        )
        resposta = self.client.get(reverse("solicitacoes:lista"), {"fila": "proximos"})
        self.assertEqual(self._ids(resposta), {proxima.pk})

    def test_status_da_url_aparece_com_x_e_nao_acende_todas(self):
        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"status": StatusSolicitacao.AGUARDANDO_DESPACHO}
        )
        self.assertEqual(self._ids(resposta), {self.aguardando.pk})
        self.assertContains(resposta, "Situação: Aguardando despacho")
        self.assertNotEqual(resposta.context["situacao_ativa"], "todas")
        [filtro] = resposta.context["filtros_ativos"]
        self.assertNotIn("status=", filtro["url_remover"])

    def test_trocar_de_fila_substitui_o_status(self):
        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"status": StatusSolicitacao.DEFERIDA_EM_ANDAMENTO}
        )
        despacho = next(i for i in resposta.context["situacoes"] if i["slug"] == "despacho")
        self.assertNotIn("status=", despacho["url"])

    def test_busca_mantem_o_periodo(self):
        resposta = self.client.get(
            reverse("solicitacoes:lista"), {"inicio": "2026-01-01", "fim": "2026-12-31"}
        )
        self.assertContains(resposta, 'type="hidden" name="inicio" value="2026-01-01"')
        self.assertContains(resposta, 'type="hidden" name="fim" value="2026-12-31"')
        self.assertContains(resposta, "Eventos a partir de 01/01/2026")

    def test_cartoes_do_dashboard_usam_as_filas(self):
        resposta = self.client.get(reverse("dashboard:index"))
        urls = [cartao["url"] for cartao in resposta.context["resumo"]]
        self.assertIn(reverse("solicitacoes:lista") + "?fila=despacho", urls)
        self.assertIn(reverse("solicitacoes:lista") + "?fila=deferidas_ano", urls)
        self.assertIn(reverse("solicitacoes:lista") + "?fila=proximos", urls)
        self.assertFalse(any("status=" in url for url in urls))


class ObservacaoLongaTests(BaseSolicitacaoTestCase):
    """Observação longa da DG não pode derrubar o despacho (aviso do sino tem limite)."""

    LONGA = "Justificativa detalhada da Diretoria-Geral. " * 12  # ~500 caracteres

    def _limites_ok(self, solicitacao):
        from core.models import Notificacao

        avisos = Notificacao.objects.filter(solicitacao=solicitacao)
        self.assertTrue(avisos.exists())
        for aviso in avisos:
            self.assertLessEqual(len(aviso.mensagem), 255)
            self.assertLessEqual(len(aviso.titulo), 150)

    def test_devolver_com_observacao_longa(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.devolver(solicitacao, self.gestor, self.LONGA)
        self._limites_ok(solicitacao)
        # A íntegra fica no histórico.
        self.assertEqual(solicitacao.historico.last().observacao, self.LONGA.strip())

    def test_despachar_com_observacao_longa(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.despachar(solicitacao, self.gestor, DecisaoDG.NAO_ATENDER, self.LONGA)
        self._limites_ok(solicitacao)
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.observacoes_dg, self.LONGA.strip())

    def test_cancelar_evento_com_observacao_longa(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        services.cancelar_evento(solicitacao, self.solicitante, self.LONGA)
        self._limites_ok(solicitacao)

    def test_reenviar_com_muitas_alteracoes(self):
        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        alteracoes = [
            {"campo": f"Campo alterado número {i}", "antes": "a", "depois": "b"}
            for i in range(40)
        ]
        services.reenviar_apos_edicao(solicitacao, self.solicitante, alteracoes)
        self._limites_ok(solicitacao)
        self.assertEqual(len(solicitacao.historico.last().alteracoes), 40)

    def test_falha_de_banco_no_despacho_volta_com_mensagem(self):
        """Erro de banco não vira página 500: a DG volta ao despacho com o texto."""
        from unittest.mock import patch

        from django.db import DataError

        solicitacao = self.solicitacao_completa()
        services.enviar(solicitacao, self.solicitante)
        self.client.force_login(self.gestor)
        with patch("solicitacoes.services.despachar", side_effect=DataError("value too long")):
            resposta = self.client.post(
                reverse("solicitacoes:despachar", args=[solicitacao.pk]),
                {"decisao": DecisaoDG.NAO_ATENDER, "observacao": self.LONGA},
            )
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("#despacho-dg", resposta["Location"])
        self.assertEqual(
            self.client.session["despacho_pendente"]["observacao"], self.LONGA.strip()
        )
