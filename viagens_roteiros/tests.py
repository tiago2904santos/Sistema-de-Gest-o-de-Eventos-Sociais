"""Modelos de roteiro e a gravação do cálculo de diárias.

A régua do cálculo em si está em ``tests_caracterizacao.py``; aqui se prova que
o banco defende as regras por conta própria e que o resultado do motor chega
íntegro às tabelas.
"""

import re
from datetime import date, datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Estado, Municipio, Regiao
from viagens_cadastros.models import TabelaDiaria

from .models import Roteiro, RoteiroDestino, RoteiroDiariaComponente, RoteiroTrecho
from .services.calculo import chegada_final, marcadores_do_roteiro, recalcular_diarias
from .services.diarias import RoteiroIncalculavel


def dt(ano, mes, dia, hora, minuto=0):
    """Data e hora no fuso do sistema — é o que a produção grava."""
    return timezone.make_aware(datetime(ano, mes, dia, hora, minuto))


class BaseRoteiroTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Estados e regiões já vêm semeados por migração.
        cls.pr, _ = Estado.objects.get_or_create(
            sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41}
        )
        cls.sp, _ = Estado.objects.get_or_create(
            sigla="SP", defaults={"nome": "São Paulo", "codigo_ibge": 35}
        )
        cls.capital, _ = Regiao.objects.get_or_create(nome="Capital")
        cls.interior, _ = Regiao.objects.get_or_create(nome="Interior")
        cls.curitiba, _ = Municipio.objects.get_or_create(
            nome="Curitiba", estado=cls.pr, defaults={"regiao": cls.capital}
        )
        cls.abatia, _ = Municipio.objects.get_or_create(
            nome="Abatiá", estado=cls.pr, defaults={"regiao": cls.interior}
        )
        cls.sao_paulo, _ = Municipio.objects.get_or_create(
            nome="São Paulo", estado=cls.sp, defaults={"regiao": cls.capital}
        )
        for faixa, valor in (
            (TabelaDiaria.Faixa.INTERIOR, Decimal("290.55")),
            (TabelaDiaria.Faixa.CAPITAL, Decimal("371.26")),
            (TabelaDiaria.Faixa.BRASILIA, Decimal("468.12")),
        ):
            TabelaDiaria.objects.create(
                faixa=faixa, vigencia_inicio=date(2026, 1, 1), valor_24h=valor
            )

    def roteiro_curitiba_sp_abatia(self):
        """O roteiro do demonstrativo oficial de R$ 773,19, montado no banco."""
        roteiro = Roteiro.objects.create(
            origem_municipio=self.curitiba,
            saida_dt=dt(2026, 8, 12, 8, 0),
            retorno_chegada_dt=dt(2026, 8, 14, 18, 0),
            quantidade_servidores=1,
        )
        RoteiroTrecho.objects.create(
            roteiro=roteiro,
            ordem=1,
            origem_municipio=self.curitiba,
            destino_municipio=self.sao_paulo,
            saida_dt=dt(2026, 8, 12, 8, 0),
            chegada_dt=dt(2026, 8, 12, 18, 0),
        )
        RoteiroTrecho.objects.create(
            roteiro=roteiro,
            ordem=2,
            origem_municipio=self.sao_paulo,
            destino_municipio=self.abatia,
            saida_dt=dt(2026, 8, 13, 8, 0),
            chegada_dt=dt(2026, 8, 13, 18, 0),
        )
        RoteiroTrecho.objects.create(
            roteiro=roteiro,
            ordem=3,
            origem_municipio=self.abatia,
            destino_municipio=self.curitiba,
            saida_dt=dt(2026, 8, 14, 8, 0),
            chegada_dt=dt(2026, 8, 14, 18, 0),
        )
        return roteiro


class ConstraintsDoRoteiroTests(BaseRoteiroTestCase):
    def test_banco_recusa_volta_anterior_a_saida(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Roteiro.objects.create(
                    saida_dt=dt(2026, 8, 14, 8, 0),
                    retorno_chegada_dt=dt(2026, 8, 12, 8, 0),
                )

    def test_banco_aceita_ida_e_volta_no_mesmo_instante(self):
        # Degenerado, não impossível: o que se barra é a inversão.
        instante = dt(2026, 8, 12, 8, 0)
        roteiro = Roteiro.objects.create(saida_dt=instante, retorno_chegada_dt=instante)
        self.assertIsNotNone(roteiro.pk)

    def test_banco_aceita_roteiro_com_datas_em_branco(self):
        # Rascunho começa vazio; a constraint só se aplica quando há as duas datas.
        self.assertIsNotNone(Roteiro.objects.create().pk)

    def test_banco_recusa_valor_de_diarias_negativo(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Roteiro.objects.create(valor_diarias=Decimal("-1.00"))

    def test_destino_nao_repete_ordem_no_mesmo_roteiro(self):
        roteiro = Roteiro.objects.create()
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.abatia, ordem=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RoteiroDestino.objects.create(
                    roteiro=roteiro, municipio=self.sao_paulo, ordem=1
                )

    def test_trecho_nao_aceita_chegada_antes_da_saida(self):
        roteiro = Roteiro.objects.create()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RoteiroTrecho.objects.create(
                    roteiro=roteiro,
                    ordem=1,
                    saida_dt=dt(2026, 8, 12, 18, 0),
                    chegada_dt=dt(2026, 8, 12, 8, 0),
                )

    def test_trecho_nao_aceita_distancia_negativa(self):
        roteiro = Roteiro.objects.create()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RoteiroTrecho.objects.create(
                    roteiro=roteiro, ordem=1, distancia_km=Decimal("-5.00")
                )

    def test_parcela_de_diaria_exige_quantidade_positiva(self):
        roteiro = Roteiro.objects.create()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RoteiroDiariaComponente.objects.create(
                    roteiro=roteiro,
                    ordem=1,
                    faixa="INTERIOR",
                    percentual=100,
                    quantidade=0,
                    valor_unitario=Decimal("290.55"),
                    subtotal=Decimal("0.00"),
                )


class CancelamentoTests(BaseRoteiroTestCase):
    def test_cancelar_guarda_o_motivo_e_a_data(self):
        roteiro = Roteiro.objects.create()
        roteiro.cancelar("Evento adiado")
        roteiro.refresh_from_db()
        self.assertTrue(roteiro.cancelado)
        self.assertEqual(roteiro.motivo_cancelamento, "Evento adiado")
        self.assertIsNotNone(roteiro.cancelado_em)

    def test_reativar_limpa_o_cancelamento(self):
        roteiro = Roteiro.objects.create()
        roteiro.cancelar("Engano")
        roteiro.reativar()
        roteiro.refresh_from_db()
        self.assertFalse(roteiro.cancelado)
        self.assertEqual(roteiro.motivo_cancelamento, "")
        self.assertIsNone(roteiro.cancelado_em)


class MarcadoresTests(BaseRoteiroTestCase):
    def test_cada_trecho_de_ida_vira_um_marcador_na_ordem(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        marcadores = marcadores_do_roteiro(roteiro)
        self.assertEqual(
            [(m.destino_cidade, m.destino_uf) for m in marcadores],
            [("São Paulo", "SP"), ("Abatiá", "PR"), ("Curitiba", "PR")],
        )

    def test_trecho_de_retorno_nao_vira_marcador(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        roteiro.trechos.filter(ordem=3).update(sentido=RoteiroTrecho.Sentido.RETORNO)
        self.assertEqual(len(marcadores_do_roteiro(roteiro)), 2)

    def test_trecho_sem_destino_e_ignorado(self):
        roteiro = Roteiro.objects.create()
        RoteiroTrecho.objects.create(
            roteiro=roteiro, ordem=1, saida_dt=dt(2026, 8, 12, 8, 0)
        )
        self.assertEqual(marcadores_do_roteiro(roteiro), [])

    def test_sem_retorno_a_chegada_final_e_a_do_ultimo_trecho(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        Roteiro.objects.filter(pk=roteiro.pk).update(retorno_chegada_dt=None)
        roteiro.refresh_from_db()
        self.assertEqual(chegada_final(roteiro), dt(2026, 8, 14, 18, 0))


class GravacaoDoCalculoTests(BaseRoteiroTestCase):
    def test_o_roteiro_do_demonstrativo_grava_o_valor_oficial(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        roteiro.refresh_from_db()
        self.assertEqual(roteiro.valor_diarias, Decimal("773.19"))
        self.assertEqual(roteiro.resumo_diarias, "2 x 100% + 1 x 30%")
        self.assertIn("setecentos", roteiro.valor_diarias_extenso)

    def test_a_composicao_gravada_soma_o_total(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        parcelas = roteiro.componentes_diarias.all()
        self.assertEqual(parcelas.count(), 3)
        self.assertEqual(
            sum(p.subtotal for p in parcelas), Decimal("773.19")
        )
        self.assertEqual([p.ordem for p in parcelas], [1, 2, 3])

    def test_cada_parcela_aponta_a_vigencia_que_a_sustentou(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        for parcela in roteiro.componentes_diarias.all():
            self.assertIsNotNone(parcela.tabela_diaria_id)
            self.assertEqual(parcela.tabela_vigencia_inicio, date(2026, 1, 1))

    def test_recalcular_substitui_as_parcelas_em_vez_de_acumular(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        primeiras = list(roteiro.componentes_diarias.values_list("pk", flat=True))
        recalcular_diarias(roteiro)
        segundas = list(roteiro.componentes_diarias.values_list("pk", flat=True))
        self.assertEqual(len(segundas), 3)
        self.assertFalse(set(primeiras) & set(segundas))

    def test_equipe_maior_multiplica_o_total(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        roteiro.quantidade_servidores = 3
        roteiro.save(update_fields=["quantidade_servidores"])
        recalcular_diarias(roteiro)
        roteiro.refresh_from_db()
        self.assertEqual(roteiro.valor_diarias, Decimal("773.19") * 3)

    def test_o_horario_exibido_e_o_local_e_nao_o_do_banco(self):
        """Datas vêm do banco em UTC; exibi-las cruas adiantaria 3 horas.

        O operador digitou 08:00 e é 08:00 que tem de sair no documento — não
        as 11:00 em que o instante está gravado.
        """
        roteiro = self.roteiro_curitiba_sp_abatia()
        roteiro.refresh_from_db()
        resultado = recalcular_diarias(roteiro)
        primeiro = resultado["trechos"][0]
        self.assertEqual(primeiro["data_saida"], "12/08/2026")
        self.assertEqual(primeiro["hora_saida"], "08:00")

    def test_roteiro_sem_trecho_recusa_o_calculo(self):
        roteiro = Roteiro.objects.create(origem_municipio=self.curitiba)
        with self.assertRaises(RoteiroIncalculavel):
            recalcular_diarias(roteiro)

    def test_a_vigencia_protege_as_parcelas_ja_gravadas(self):
        # Apagar uma vigência usada apagaria a explicação de um pagamento.
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        tabela = roteiro.componentes_diarias.first().tabela_diaria
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            tabela.delete()


class BaseTelaRoteiroTestCase(BaseRoteiroTestCase):
    """Usuário com o módulo VIAGENS — o mínimo para abrir as telas."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from accounts.models import Modulo, Setor

        cls.setor, _ = Setor.objects.get_or_create(
            nome="ASCOM", defaults={"sigla": "ASCOM"}
        )
        cls.modulo = Modulo.objects.get(codigo="VIAGENS")
        cls.modulo.setores.add(cls.setor)

    def criar_usuario(self, username, *grupos):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group

        User = get_user_model()
        usuario = User.objects.create_user(username=username)
        usuario.setores.add(self.setor)
        for nome in grupos:
            usuario.groups.add(Group.objects.get(name=nome))
        return usuario


class AcessoAsTelasTests(BaseTelaRoteiroTestCase):
    def test_sem_o_modulo_a_lista_e_negada(self):
        from django.contrib.auth import get_user_model

        self.client.force_login(get_user_model().objects.create_user("forasteiro"))
        resposta = self.client.get(reverse("viagens_roteiros:lista"))
        self.assertEqual(resposta.status_code, 403)

    def test_com_o_modulo_a_lista_abre(self):
        self.client.force_login(self.criar_usuario("leitora"))
        resposta = self.client.get(reverse("viagens_roteiros:lista"))
        self.assertEqual(resposta.status_code, 200)

    def test_quem_so_consulta_nao_monta_roteiro(self):
        self.client.force_login(self.criar_usuario("leitora2"))
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        self.assertEqual(resposta.status_code, 403)

    def test_quem_so_consulta_nao_dispara_o_calculo(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        self.client.force_login(self.criar_usuario("leitora3"))
        resposta = self.client.post(
            reverse("viagens_roteiros:calcular", args=[roteiro.pk])
        )
        self.assertEqual(resposta.status_code, 403)
        roteiro.refresh_from_db()
        self.assertIsNone(roteiro.valor_diarias)


class TelaDeListaTests(BaseTelaRoteiroTestCase):
    def setUp(self):
        self.client.force_login(self.criar_usuario("operadora", "VIAGENS_OPERADOR"))

    def test_a_lista_mostra_o_percurso_sem_repetir_a_sede_no_fim(self):
        self.roteiro_curitiba_sp_abatia()
        resposta = self.client.get(reverse("viagens_roteiros:lista"))
        self.assertContains(resposta, "São Paulo → Abatiá")

    def test_busca_encontra_pelo_municipio_de_destino(self):
        self.roteiro_curitiba_sp_abatia()
        Roteiro.objects.create(origem_municipio=self.curitiba)
        resposta = self.client.get(
            reverse("viagens_roteiros:lista"), {"q": "Abatiá"}
        )
        self.assertEqual(len(resposta.context["linhas"]), 1)

    def test_filtro_de_situacao_separa_cancelados(self):
        cancelado = Roteiro.objects.create(origem_municipio=self.curitiba)
        cancelado.cancelar("Adiado")
        Roteiro.objects.create(origem_municipio=self.curitiba)
        resposta = self.client.get(
            reverse("viagens_roteiros:lista"), {"situacao": "cancelados"}
        )
        self.assertEqual(len(resposta.context["linhas"]), 1)


class MontagemPelaTelaTests(BaseTelaRoteiroTestCase):
    def setUp(self):
        self.client.force_login(self.criar_usuario("operadora2", "VIAGENS_OPERADOR"))

    def dados(self, **extras):
        base = {
            "origem_municipio": self.curitiba.pk,
            "quantidade_servidores": 1,
            "observacoes": "",
            "trechos-TOTAL_FORMS": "1",
            "trechos-INITIAL_FORMS": "0",
            "trechos-MIN_NUM_FORMS": "0",
            "trechos-MAX_NUM_FORMS": "1000",
            "trechos-0-ordem": "1",
            "trechos-0-origem_municipio": self.curitiba.pk,
            "trechos-0-destino_municipio": self.sao_paulo.pk,
            "trechos-0-saida_dt": "2026-08-12T08:00",
            "trechos-0-chegada_dt": "2026-08-12T18:00",
            "trechos-0-distancia_km": "",
        }
        base.update(extras)
        return base

    def test_criar_roteiro_com_um_trecho(self):
        resposta = self.client.post(reverse("viagens_roteiros:novo"), self.dados())
        roteiro = Roteiro.objects.latest("pk")
        self.assertRedirects(
            resposta, reverse("viagens_roteiros:detalhe", args=[roteiro.pk])
        )
        self.assertEqual(roteiro.trechos.count(), 1)
        self.assertEqual(roteiro.trechos.get().destino_municipio, self.sao_paulo)

    def test_roteiro_sem_solicitacao_nasce_avulso(self):
        self.client.post(reverse("viagens_roteiros:novo"), self.dados())
        self.assertEqual(Roteiro.objects.latest("pk").tipo, Roteiro.Tipo.AVULSO)

    def test_vincular_solicitacao_marca_o_roteiro_como_de_evento(self):
        from django.contrib.auth import get_user_model
        from solicitacoes.models import SolicitacaoEvento

        criador = get_user_model().objects.create_user("criadora")
        solicitacao = SolicitacaoEvento.objects.create(criado_por=criador)
        self.client.post(
            reverse("viagens_roteiros:novo"), self.dados(solicitacao=solicitacao.pk)
        )
        roteiro = Roteiro.objects.latest("pk")
        self.assertEqual(roteiro.tipo, Roteiro.Tipo.EVENTO)
        self.assertEqual(roteiro.solicitacao_id, solicitacao.pk)

    def test_chegada_antes_da_saida_e_recusada_na_tela(self):
        resposta = self.client.post(
            reverse("viagens_roteiros:novo"),
            self.dados(**{"trechos-0-chegada_dt": "2026-08-12T06:00"}),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "não pode ser anterior à saída")

    def test_trecho_com_saida_e_sem_destino_e_recusado(self):
        resposta = self.client.post(
            reverse("viagens_roteiros:novo"),
            self.dados(**{"trechos-0-destino_municipio": ""}),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Informe o destino do trecho")

    def test_editar_roteiro_existente_preserva_o_vinculo(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        resposta = self.client.get(
            reverse("viagens_roteiros:editar", args=[roteiro.pk])
        )
        self.assertEqual(resposta.status_code, 200)
        # Os três trechos gravados aparecem preenchidos no formulário.
        self.assertEqual(resposta.context["formset"].initial_form_count(), 3)


class CalculoPelaTelaTests(BaseTelaRoteiroTestCase):
    def setUp(self):
        self.client.force_login(self.criar_usuario("gestora", "VIAGENS_GESTOR"))

    def test_calcular_grava_o_valor_do_demonstrativo_e_avisa(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        resposta = self.client.post(
            reverse("viagens_roteiros:calcular", args=[roteiro.pk]), follow=True
        )
        roteiro.refresh_from_db()
        self.assertEqual(roteiro.valor_diarias, Decimal("773.19"))
        self.assertContains(resposta, "773,19")

    def test_o_detalhe_mostra_a_composicao_depois_do_calculo(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        resposta = self.client.get(
            reverse("viagens_roteiros:detalhe", args=[roteiro.pk])
        )
        self.assertEqual(len(resposta.context["parcelas"]), 3)
        self.assertContains(resposta, "CAPITAL")

    def test_roteiro_sem_trecho_avisa_em_vez_de_quebrar(self):
        roteiro = Roteiro.objects.create(origem_municipio=self.curitiba)
        resposta = self.client.post(
            reverse("viagens_roteiros:calcular", args=[roteiro.pk]), follow=True
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "antes de calcular")

    def test_sem_vigencia_cadastrada_a_tela_diz_o_que_falta(self):
        TabelaDiaria.objects.all().delete()
        roteiro = self.roteiro_curitiba_sp_abatia()
        resposta = self.client.post(
            reverse("viagens_roteiros:calcular", args=[roteiro.pk]), follow=True
        )
        self.assertContains(resposta, "Cadastre a vigência")
        roteiro.refresh_from_db()
        self.assertIsNone(roteiro.valor_diarias)


class CicloDeVidaPelaTelaTests(BaseTelaRoteiroTestCase):
    def setUp(self):
        self.client.force_login(self.criar_usuario("operadora3", "VIAGENS_OPERADOR"))

    def test_cancelar_exige_motivo(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        self.client.post(
            reverse("viagens_roteiros:cancelar", args=[roteiro.pk]), {"motivo": ""}
        )
        roteiro.refresh_from_db()
        self.assertFalse(roteiro.cancelado)

    def test_cancelar_e_reativar_pela_tela(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        self.client.post(
            reverse("viagens_roteiros:cancelar", args=[roteiro.pk]),
            {"motivo": "Evento adiado"},
        )
        roteiro.refresh_from_db()
        self.assertTrue(roteiro.cancelado)
        self.assertEqual(roteiro.motivo_cancelamento, "Evento adiado")

        self.client.post(reverse("viagens_roteiros:reativar", args=[roteiro.pk]))
        roteiro.refresh_from_db()
        self.assertFalse(roteiro.cancelado)

    def test_excluir_remove_o_roteiro_e_suas_parcelas(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        self.client.post(reverse("viagens_roteiros:excluir", args=[roteiro.pk]))
        self.assertFalse(Roteiro.objects.filter(pk=roteiro.pk).exists())
        self.assertEqual(RoteiroDiariaComponente.objects.count(), 0)


class DefeitosEncontradosNoSmokeTests(BaseTelaRoteiroTestCase):
    """Cada teste aqui reproduz algo que só apareceu ao abrir a tela de verdade.

    Nenhum deles falhava no motor nem nos modelos: eram defeitos de
    apresentação e de formulário, o tipo de coisa que passa por uma suíte que
    só olha para o banco.
    """

    def setUp(self):
        self.client.force_login(self.criar_usuario("smoke", "VIAGENS_GESTOR"))

    def dados_com_linha_em_branco(self, ordem_da_linha_vazia="3"):
        return {
            "origem_municipio": self.curitiba.pk,
            "quantidade_servidores": 1,
            "observacoes": "",
            "trechos-TOTAL_FORMS": "2",
            "trechos-INITIAL_FORMS": "0",
            "trechos-MIN_NUM_FORMS": "0",
            "trechos-MAX_NUM_FORMS": "1000",
            "trechos-0-ordem": "1",
            "trechos-0-origem_municipio": self.curitiba.pk,
            "trechos-0-destino_municipio": self.sao_paulo.pk,
            "trechos-0-saida_dt": "2026-08-12T08:00",
            "trechos-0-chegada_dt": "2026-08-12T18:00",
            "trechos-0-distancia_km": "",
            # Só a ordem mexida — o resto em branco, como quem numera as linhas
            # antes de preenchê-las.
            "trechos-1-ordem": ordem_da_linha_vazia,
            "trechos-1-origem_municipio": "",
            "trechos-1-destino_municipio": "",
            "trechos-1-saida_dt": "",
            "trechos-1-chegada_dt": "",
            "trechos-1-distancia_km": "",
        }

    def test_linha_so_com_a_ordem_mexida_nao_vira_trecho(self):
        # `ordem` tem default=1: mudar só esse número marcava o formulário como
        # alterado e gravava um trecho sem destino nem datas, contrariando o
        # "linhas em branco são ignoradas" escrito na própria tela.
        self.client.post(
            reverse("viagens_roteiros:novo"), self.dados_com_linha_em_branco()
        )
        self.assertEqual(Roteiro.objects.latest("pk").trechos.count(), 1)

    def test_esvaziar_um_trecho_gravado_nao_o_apaga_em_silencio(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        trecho = roteiro.trechos.first()
        resposta = self.client.post(
            reverse("viagens_roteiros:editar", args=[roteiro.pk]),
            {
                "origem_municipio": self.curitiba.pk,
                "quantidade_servidores": 1,
                "observacoes": "",
                "trechos-TOTAL_FORMS": "1",
                "trechos-INITIAL_FORMS": "1",
                "trechos-MIN_NUM_FORMS": "0",
                "trechos-MAX_NUM_FORMS": "1000",
                "trechos-0-id": trecho.pk,
                "trechos-0-ordem": "1",
                "trechos-0-origem_municipio": "",
                "trechos-0-destino_municipio": "",
                "trechos-0-saida_dt": "",
                "trechos-0-chegada_dt": "",
                "trechos-0-distancia_km": "",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(roteiro.trechos.filter(pk=trecho.pk).exists())
        # E o operador precisa ler por que a gravação não passou.
        self.assertContains(resposta, "Trecho sem dados")

    def test_os_campos_do_formulario_saem_com_a_classe_do_design_system(self):
        # Sem isso o navegador desenha os controles nativos no meio de uma tela
        # estilizada — o formulário parecia de outro sistema.
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        corpo = resposta.content.decode()
        for campo in ("origem_municipio", "quantidade_servidores", "observacoes"):
            with self.subTest(campo=campo):
                marcacao = re.search(
                    r'<(?:input|select|textarea)[^>]*name="%s"[^>]*>' % campo, corpo
                )
                self.assertIsNotNone(marcacao, "campo %s não renderizou" % campo)
                self.assertIn("form-controle", marcacao.group(0))

    def test_a_opcao_vazia_dos_selects_fala_portugues(self):
        # O padrão do Django ("Select an option") vinha em inglês no meio de uma
        # tela em português; o resto do sistema diz "Selecione...".
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        self.assertContains(resposta, "Selecione...")
        self.assertNotContains(resposta, "Select an option")

    def test_o_minimo_do_html_acompanha_a_validacao_do_servidor(self):
        # `clean_quantidade_servidores` recusa zero: deixar min=0 no HTML só
        # adiaria o erro para depois do envio.
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        marcacao = re.search(
            r'<input[^>]*name="quantidade_servidores"[^>]*>',
            resposta.content.decode(),
        )
        self.assertIn('min="1"', marcacao.group(0))

    def test_a_lista_diz_o_tipo_do_roteiro_para_quem_nao_ve_o_icone(self):
        # A coluna anunciava "Tipo" e entregava um ícone `aria-hidden`: para um
        # leitor de tela, uma coluna vazia.
        self.roteiro_curitiba_sp_abatia()
        resposta = self.client.get(reverse("viagens_roteiros:lista"))
        self.assertContains(resposta, "Avulso")

    def test_corrigir_um_trecho_recusado_nao_cria_um_segundo_roteiro(self):
        # Quando os trechos falham, o roteiro já foi gravado — a tela precisa
        # continuar a edição *dele*. Com `action=""` o reenvio voltava para
        # /novo/ e cada correção deixava mais um roteiro para trás.
        invalido = self.dados_com_linha_em_branco()
        invalido["trechos-0-chegada_dt"] = "2026-08-12T06:00"
        resposta = self.client.post(reverse("viagens_roteiros:novo"), invalido)
        self.assertEqual(resposta.status_code, 200)
        criados = Roteiro.objects.count()

        destino = re.search(
            r'<form method="post" action="([^"]*)" class="card cadastro-form"',
            resposta.content.decode(),
        ).group(1)
        self.assertTrue(destino, "o formulário precisa apontar para o roteiro gravado")

        corrigido = dict(invalido, **{"trechos-0-chegada_dt": "2026-08-12T18:00"})
        self.client.post(destino, corrigido)
        self.assertEqual(Roteiro.objects.count(), criados)

    def test_as_linhas_novas_ja_vem_numeradas_em_sequencia(self):
        # Com `default=1` em todas, preencher duas linhas sem tocar no número
        # — o caminho natural — batia na unicidade de (roteiro, ordem) logo no
        # primeiro envio.
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        ordens = re.findall(
            r'name="trechos-\d+-ordem"[^>]*value="(\d+)"', resposta.content.decode()
        )
        self.assertEqual(ordens, ["1", "2", "3"])

    def test_editar_continua_numerando_a_partir_dos_trechos_gravados(self):
        roteiro = self.roteiro_curitiba_sp_abatia()  # 3 trechos gravados
        resposta = self.client.get(reverse("viagens_roteiros:editar", args=[roteiro.pk]))
        ordens = re.findall(
            r'name="trechos-\d+-ordem"[^>]*value="(\d+)"', resposta.content.decode()
        )
        # Os três gravados mantêm a ordem que têm; as três linhas novas seguem.
        self.assertEqual(ordens[3:], ["4", "5", "6"])
