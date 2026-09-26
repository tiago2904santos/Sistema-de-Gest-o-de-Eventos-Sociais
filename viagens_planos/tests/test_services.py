"""As regras portadas: numeração, textos padrão, coordenação, período extenso, efetivo e pendências."""

from datetime import date, time
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from viagens_planos.models import EfetivoPlano, PlanoTrabalho
from viagens_planos.services import (
    aplicar_textos_padrao,
    avaliar_pendencias_documento,
    criar_plano_rascunho,
    format_periodo_evento_extenso,
    montar_efetivo_texto,
    montar_texto_coordenacao,
    salvar_plano_numerado,
    sincronizar_textos_padrao,
    texto_padrao_contextualizacao,
)

from .fixtures import CenarioPlanoMixin


class NumeracaoTests(CenarioPlanoMixin, TestCase):
    def test_numeracao_sequencial(self):
        ano = timezone.localdate().year
        p1 = salvar_plano_numerado(PlanoTrabalho())
        p2 = salvar_plano_numerado(PlanoTrabalho())
        self.assertEqual((p1.numero, p1.ano), (1, ano))
        self.assertEqual((p2.numero, p2.ano), (2, ano))
        self.assertEqual(p1.numero_formatado, f"01/{ano}/ASCOM")

    def test_numero_liberado_por_exclusao_e_reaproveitado(self):
        # A regra do número de ofício: a lacuna volta antes do maior + 1.
        from viagens_planos.models import PlanoTrabalhoNumeroLacuna
        from viagens_planos.services import excluir_plano
        p1, p2, p3 = (salvar_plano_numerado(PlanoTrabalho()) for _ in range(3))
        excluir_plano(p2)
        self.assertTrue(PlanoTrabalhoNumeroLacuna.objects.filter(numero=2).exists())
        novo = salvar_plano_numerado(PlanoTrabalho())
        self.assertEqual(novo.numero, 2)
        self.assertFalse(PlanoTrabalhoNumeroLacuna.objects.exists())
        self.assertEqual(salvar_plano_numerado(PlanoTrabalho()).numero, 4)

    def test_numero_digitado_ocupa_a_lacuna(self):
        from viagens_planos.models import PlanoTrabalhoNumeroLacuna
        ano = timezone.localdate().year
        PlanoTrabalhoNumeroLacuna.objects.create(ano=ano, numero=5)
        PlanoTrabalho.objects.create(numero=5, ano=ano)
        self.assertFalse(PlanoTrabalhoNumeroLacuna.objects.exists())

    def test_contador_antigo_da_configuracao_nao_pesa_mais(self):
        self.cfg.pt_ano = timezone.localdate().year - 1
        self.cfg.pt_ultimo_numero = 42
        self.cfg.save()
        plano = salvar_plano_numerado(PlanoTrabalho())
        self.assertEqual((plano.numero, plano.ano), (1, timezone.localdate().year))

    def test_piso_no_maior_numero_do_banco(self):
        ano = timezone.localdate().year
        PlanoTrabalho.objects.create(numero=77, ano=ano)
        plano = salvar_plano_numerado(PlanoTrabalho())
        self.assertEqual(plano.numero, 78)

    def test_numero_existente_nao_e_sobrescrito(self):
        plano = salvar_plano_numerado(PlanoTrabalho(numero=20, ano=2026, sufixo_numero="ASCOM"))
        self.assertEqual(plano.numero_formatado, "20/2026/ASCOM")

    def test_colisao_repete_a_escolha(self):
        ano = timezone.localdate().year
        PlanoTrabalho.objects.create(numero=77, ano=ano)
        original = PlanoTrabalho.proximo_numero.__func__
        chamadas = []

        def colidindo(cls):
            chamadas.append(1)
            if len(chamadas) == 1:
                return 77, ano, "ASCOM"
            return original(cls)

        with mock.patch.object(PlanoTrabalho, "proximo_numero", classmethod(colidindo)):
            plano = criar_plano_rascunho()
        self.assertEqual(len(chamadas), 2)
        self.assertEqual(plano.numero, 78)

    def test_falha_ao_gravar_nao_deixa_plano(self):
        with mock.patch.object(PlanoTrabalho, "save", side_effect=RuntimeError("falha")):
            with self.assertRaisesRegex(RuntimeError, "falha"):
                salvar_plano_numerado(PlanoTrabalho())
        self.assertFalse(PlanoTrabalho.objects.exists())


class RascunhoDaViagemTests(CenarioPlanoMixin, TestCase):
    def test_rascunho_avulso_usa_o_coordenador_da_configuracao(self):
        self.cfg.coordenador_adm_plano_trabalho = self.chefia
        self.cfg.save()
        plano = criar_plano_rascunho()
        self.assertEqual(plano.coordenador_adm, self.chefia)
        self.assertIsNone(plano.coordenador_op)
        self.assertTrue(plano.contextualizacao_auto)

    def test_rascunho_da_viagem_herda_semente(self):
        from viagens_viagem.models import Viagem

        viagem = Viagem.objects.create(
            titulo="PCPR na Comunidade em Maringá", destino_estado=self.uf, destino_municipio=self.maringa,
            destinos_extras=[{"estado": self.uf.pk, "municipio": self.sarandi.pk}],
            data_inicio=date(2026, 6, 25), data_fim=date(2026, 6, 27), horario_inicio=time(9, 0), horario_fim=time(17, 0),
            responsavel=self.juliana, motivo="Motivo curto",
        )
        plano = criar_plano_rascunho(viagem=viagem)
        self.assertEqual(plano.viagem, viagem)
        self.assertEqual(plano.coordenador_adm, self.juliana)  # sem coordenador na configuração, vale o responsável
        self.assertEqual(plano.coordenador_op, self.juliana)
        self.assertEqual(plano.destino_cidade, self.maringa)
        self.assertEqual((plano.data_evento_inicio, plano.data_evento_fim), (date(2026, 6, 25), date(2026, 6, 27)))
        self.assertEqual(plano.programa_outros, "PCPR na Comunidade em Maringá")
        self.assertEqual(plano.horario_atendimento, "09:00 até 17:00")
        self.assertEqual(plano.contextualizacao, "")
        self.assertEqual([d.cidade for d in plano.destinos_rascunho()], [self.maringa, self.sarandi])


class TextosPadraoTests(CenarioPlanoMixin, TestCase):
    def test_contextualizacao_usa_municipio_e_programa(self):
        plano = self.criar_plano_maringa()
        plano.programa = self.programa
        texto = texto_padrao_contextualizacao(plano)
        self.assertIn("município de Maringá/PR", texto)
        self.assertIn("Programa Paraná em Ação", texto)
        self.assertIn("PCPR na Comunidade", texto)

    def test_aplicar_preenche_so_os_vazios(self):
        plano = self.criar_plano_maringa()
        plano.consideracao_final = "Texto editado pelo usuário."
        self.assertEqual(aplicar_textos_padrao(plano), ["contextualizacao"])
        self.assertEqual(plano.consideracao_final, "Texto editado pelo usuário.")

    def test_sincronizar_respeita_as_flags(self):
        plano = self.criar_plano_maringa()
        plano.contextualizacao = "Mantido pelo usuário."
        plano.contextualizacao_auto = False
        plano.coordenacao_auto = False
        self.assertEqual(sincronizar_textos_padrao(plano), ["consideracao_final"])
        self.assertEqual(plano.contextualizacao, "Mantido pelo usuário.")
        self.assertIn("Maringá/PR", plano.consideracao_final)


class CoordenacaoTests(CenarioPlanoMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plano = self.criar_plano_maringa()

    def test_servidor_do_banco(self):
        self.plano.coordenador_adm = self.juliana
        texto = montar_texto_coordenacao(self.plano)
        self.assertIn("Coordenador Administrativo", texto)
        self.assertIn("Papiloscopista Juliana Villela de Barros", texto)
        self.assertNotIn("Operacional", texto)

    def test_feminino(self):
        self.plano.coordenador_adm = self.juliana
        self.plano.coordenador_adm_genero = PlanoTrabalho.COORDENADOR_GENERO_FEMININO
        texto = montar_texto_coordenacao(self.plano)
        self.assertIn("Fica designada como Coordenadora Administrativa do Plano a Papiloscopista", texto)
        self.assertIn("a qual ficará responsável", texto)

    def test_manual_e_operacional_opcional(self):
        self.plano.coordenador_adm_modo = PlanoTrabalho.COORDENADOR_MODO_MANUAL
        self.plano.coordenador_adm_nome_manual = "Maria da Silva"
        self.plano.coordenador_adm_cargo_manual = "Investigadora"
        self.plano.coordenador_op_modo = PlanoTrabalho.COORDENADOR_MODO_MANUAL
        self.plano.coordenador_op_nome_manual = "José Pereira"
        self.plano.coordenador_op_cargo_manual = "Escrivão"
        texto = montar_texto_coordenacao(self.plano)
        self.assertIn("Investigadora Maria da Silva", texto)
        self.assertIn("Coordenador Operacional do Evento o Escrivão José Pereira", texto)


class PeriodoExtensoTests(TestCase):
    def test_formatos(self):
        self.assertEqual(format_periodo_evento_extenso(date(2026, 6, 25), date(2026, 6, 27)), "25 a 27 de junho de 2026")
        self.assertEqual(format_periodo_evento_extenso(date(2026, 6, 30), date(2026, 7, 2)), "30 de junho a 02 de julho de 2026")
        self.assertEqual(format_periodo_evento_extenso(date(2026, 6, 25), date(2026, 6, 25)), "25 de junho de 2026")
        self.assertEqual(format_periodo_evento_extenso(date(2025, 12, 30), date(2026, 1, 2)), "30 de dezembro de 2025 a 02 de janeiro de 2026")


class EfetivoTextoTests(CenarioPlanoMixin, TestCase):
    def test_pluraliza_por_cargo_com_sigla_da_unidade(self):
        from viagens_cadastros.models import Unidade

        plano = self.criar_plano_maringa(efetivo=2)
        iipr = Unidade.objects.create(nome="Instituto de Identificação do Paraná", sigla="IIPR")
        EfetivoPlano.objects.create(plano=plano, unidade=iipr, cargo=self.cargo_papiloscopista, quantidade=8)
        self.assertEqual(montar_efetivo_texto(plano), "2 Policiais Civis (ASCOM)\n8 Papiloscopistas (IIPR)")

    def test_sem_unidade_nao_abre_parenteses(self):
        plano = self.criar_plano_maringa()
        plano.efetivos.all().delete()
        EfetivoPlano.objects.create(plano=plano, cargo=self.cargo_papiloscopista, quantidade=1)
        self.assertEqual(montar_efetivo_texto(plano), "1 Papiloscopista")


class PendenciasTests(CenarioPlanoMixin, TestCase):
    def test_plano_vazio_lista_todas(self):
        plano = PlanoTrabalho.objects.create()
        self.assertEqual(avaliar_pendencias_documento(plano), [
            "Informe o coordenador administrativo na identificação.",
            "Informe o destino (cidade/UF) na identificação.",
            "Informe a data do evento na identificação.",
            "Informe o efetivo (cargo e quantidade) em efetivo e diárias.",
            "Calcule as diárias em efetivo e diárias.",
        ])
