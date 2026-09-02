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
            "destinos-TOTAL_FORMS": "1",
            "destinos-INITIAL_FORMS": "0",
            "destinos-MIN_NUM_FORMS": "0",
            "destinos-MAX_NUM_FORMS": "1000",
            "destinos-0-ordem": "1",
            "destinos-0-municipio": self.sao_paulo.pk,
            "trechos-TOTAL_FORMS": "1",
            "trechos-INITIAL_FORMS": "0",
            "trechos-MIN_NUM_FORMS": "0",
            "trechos-MAX_NUM_FORMS": "1000",
            "trechos-0-ordem": "1",
            "trechos-0-origem_municipio": self.curitiba.pk,
            "trechos-0-destino_municipio": self.sao_paulo.pk,
            "trechos-0-saida_data": "2026-08-12",
            "trechos-0-saida_hora": "08:00",
            "trechos-0-chegada_data": "2026-08-12",
            "trechos-0-chegada_hora": "18:00",
            "trechos-0-distancia_km": "",
        }
        base.update(extras)
        return base

    def test_criar_roteiro_com_um_trecho(self):
        resposta = self.client.post(reverse("viagens_roteiros:novo"), self.dados())
        roteiro = Roteiro.objects.latest("pk")
        self.assertRedirects(resposta, reverse("viagens_roteiros:lista"))
        self.assertEqual(roteiro.trechos.count(), 1)
        self.assertEqual(roteiro.trechos.get().destino_municipio, self.sao_paulo)

    def test_salvar_ja_calcula_as_diarias(self):
        """O cálculo acompanha o salvamento — sem passo extra de "calcular"."""
        resposta = self.client.post(
            reverse("viagens_roteiros:novo"), self.dados(), follow=True
        )
        roteiro = Roteiro.objects.latest("pk")
        self.assertIsNotNone(roteiro.valor_diarias)
        self.assertContains(resposta, "diárias")

    def test_roteiro_incompleto_salva_e_avisa_sem_erro(self):
        """Percurso sem datas não impede salvar; o aviso explica o que falta."""
        incompleto = self.dados(
            **{
                "trechos-0-saida_data": "",
                "trechos-0-saida_hora": "",
                "trechos-0-chegada_data": "",
                "trechos-0-chegada_hora": "",
            }
        )
        resposta = self.client.post(
            reverse("viagens_roteiros:novo"), incompleto, follow=True
        )
        roteiro = Roteiro.objects.latest("pk")
        self.assertIsNone(roteiro.valor_diarias)
        self.assertContains(resposta, "ainda não calculadas")

    def test_o_calendario_de_datas_abre_no_proprio_botao(self):
        """"Preencher datas de saída" é o gatilho do calendário de N datas."""
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        corpo = resposta.content.decode()
        self.assertIn("data-custom-date-multi", corpo)
        self.assertIn("data-custom-date-multi-trigger", corpo)
        self.assertIn("Preencher datas de saída", corpo)
        # O painel antigo (campo "a partir de" + aplicar) não existe mais.
        self.assertNotIn('name="datas_a_partir_de"', corpo)

    def test_a_tela_oferece_estado_para_filtrar_municipio(self):
        """Estado é filtro de tela: o município carrega o dono no `data-parent-value`."""
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        corpo = resposta.content.decode()
        self.assertIn('name="origem_estado"', corpo)
        self.assertIn('data-depends-on="id_origem_estado"', corpo)
        self.assertIn('data-parent-value="%s"' % self.curitiba.estado_id, corpo)

    def test_destinos_sao_gravados_na_ordem_da_visita(self):
        self.client.post(reverse("viagens_roteiros:novo"), self.dados())
        roteiro = Roteiro.objects.latest("pk")
        destinos = list(roteiro.destinos.values_list("municipio__nome", flat=True))
        self.assertEqual(destinos, ["São Paulo"])

    def test_rota_sem_chave_explica_a_configuracao(self):
        """Sem OPENROUTESERVICE_API_KEY o endpoint explica o que falta.

        A chave do ambiente é anulada de propósito: o teste descreve o
        comportamento sem configuração e não pode depender do `.env` local
        (nem sair chamando a API de verdade quando a chave existir).
        """
        from cadastros.models import Municipio

        Municipio.objects.filter(
            pk__in=[self.curitiba.pk, self.sao_paulo.pk]
        ).update(latitude="-25.4290000", longitude="-49.2671000")
        with self.settings(OPENROUTESERVICE_API_KEY=""):
            resposta = self.client.post(
                reverse("viagens_roteiros:calcular_rota"),
                {"municipios": [self.curitiba.pk, self.sao_paulo.pk]},
            )
        dados = resposta.json()
        self.assertFalse(dados["ok"])
        self.assertIn("OPENROUTESERVICE_API_KEY", dados["motivo"])

    def test_rota_sem_coordenadas_aponta_os_municipios(self):
        resposta = self.client.post(
            reverse("viagens_roteiros:calcular_rota"),
            {"municipios": [self.curitiba.pk, self.sao_paulo.pk]},
        )
        dados = resposta.json()
        self.assertFalse(dados["ok"])
        self.assertIn("coordenadas", dados["motivo"])

    def test_previa_devolve_o_total_sem_gravar_nada(self):
        """A prévia roda o motor sobre o formulário e não cria roteiro."""
        antes = Roteiro.objects.count()
        resposta = self.client.post(
            reverse("viagens_roteiros:previa_diarias"), self.dados()
        )
        dados = resposta.json()
        self.assertTrue(dados["ok"])
        self.assertIn("total_valor", dados["totais"])
        self.assertEqual(Roteiro.objects.count(), antes)

    def test_previa_incompleta_explica_o_que_falta(self):
        incompleto = self.dados(
            **{"trechos-0-saida_data": "", "trechos-0-saida_hora": ""}
        )
        resposta = self.client.post(
            reverse("viagens_roteiros:previa_diarias"), incompleto
        )
        dados = resposta.json()
        self.assertFalse(dados["ok"])
        self.assertIn("prévia", dados["motivo"])

    def test_previa_exige_permissao_de_edicao(self):
        from django.contrib.auth import get_user_model

        leitora = get_user_model().objects.create_user("leitora_previa")
        leitora.setores.add(self.setor)
        self.client.force_login(leitora)
        resposta = self.client.post(
            reverse("viagens_roteiros:previa_diarias"), self.dados()
        )
        self.assertEqual(resposta.status_code, 403)

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
            self.dados(**{"trechos-0-chegada_hora": "06:00"}),
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

    def test_a_edicao_mostra_a_composicao_gravada_depois_do_calculo(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        recalcular_diarias(roteiro)
        resposta = self.client.get(
            reverse("viagens_roteiros:editar", args=[roteiro.pk])
        )
        self.assertEqual(len(resposta.context["parcelas"]), 3)
        self.assertContains(resposta, "CAPITAL")
        self.assertContains(resposta, "Composição gravada no último cálculo")

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
            "destinos-TOTAL_FORMS": "0",
            "destinos-INITIAL_FORMS": "0",
            "destinos-MIN_NUM_FORMS": "0",
            "destinos-MAX_NUM_FORMS": "1000",
            "trechos-TOTAL_FORMS": "2",
            "trechos-INITIAL_FORMS": "0",
            "trechos-MIN_NUM_FORMS": "0",
            "trechos-MAX_NUM_FORMS": "1000",
            "trechos-0-ordem": "1",
            "trechos-0-origem_municipio": self.curitiba.pk,
            "trechos-0-destino_municipio": self.sao_paulo.pk,
            "trechos-0-saida_data": "2026-08-12",
            "trechos-0-saida_hora": "08:00",
            "trechos-0-chegada_data": "2026-08-12",
            "trechos-0-chegada_hora": "18:00",
            "trechos-0-distancia_km": "",
            # Só a ordem mexida — o resto em branco, como quem numera as linhas
            # antes de preenchê-las.
            "trechos-1-ordem": ordem_da_linha_vazia,
            "trechos-1-origem_municipio": "",
            "trechos-1-destino_municipio": "",
            "trechos-1-saida_data": "",
            "trechos-1-saida_hora": "",
            "trechos-1-chegada_data": "",
            "trechos-1-chegada_hora": "",
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
                "destinos-TOTAL_FORMS": "0",
                "destinos-INITIAL_FORMS": "0",
                "destinos-MIN_NUM_FORMS": "0",
                "destinos-MAX_NUM_FORMS": "1000",
                "trechos-TOTAL_FORMS": "1",
                "trechos-INITIAL_FORMS": "1",
                "trechos-MIN_NUM_FORMS": "0",
                "trechos-MAX_NUM_FORMS": "1000",
                "trechos-0-id": trecho.pk,
                "trechos-0-ordem": "1",
                "trechos-0-origem_municipio": "",
                "trechos-0-destino_municipio": "",
                "trechos-0-saida_data": "",
                "trechos-0-saida_hora": "",
                "trechos-0-chegada_data": "",
                "trechos-0-chegada_hora": "",
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
        for campo in ("origem_municipio", "roteiro_base"):
            with self.subTest(campo=campo):
                marcacao = re.search(
                    r'<(?:input|select|textarea)[^>]*name="%s"[^>]*>' % campo, corpo
                )
                self.assertIsNotNone(marcacao, "campo %s não renderizou" % campo)
                self.assertIn("form-controle", marcacao.group(0))

    def test_a_opcao_vazia_dos_selects_fala_portugues(self):
        # O padrão do Django ("Select an option") vinha em inglês no meio de uma
        # tela em português; os pickers dizem "Buscar município...".
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        self.assertContains(resposta, "Buscar município...")
        self.assertNotContains(resposta, "Select an option")

    def test_a_tela_nao_oferece_servidores_nem_observacoes(self):
        """Decisão do dono (01/09/2026): os dois campos saíram da tela.

        Fora do formulário, editar um roteiro preserva o que está gravado em
        vez de sobrescrever com vazio — é isso que este teste protege.
        """
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        corpo = resposta.content.decode()
        self.assertNotIn('name="quantidade_servidores"', corpo)
        self.assertNotIn('name="observacoes"', corpo)

    def test_editar_preserva_servidores_e_observacoes_gravados(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        Roteiro.objects.filter(pk=roteiro.pk).update(
            quantidade_servidores=4, observacoes="Combinado por telefone."
        )
        self.client.post(
            reverse("viagens_roteiros:editar", args=[roteiro.pk]),
            self.dados_com_linha_em_branco(),
        )
        roteiro.refresh_from_db()
        self.assertEqual(roteiro.quantidade_servidores, 4)
        self.assertEqual(roteiro.observacoes, "Combinado por telefone.")

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
        invalido["trechos-0-chegada_hora"] = "06:00"
        resposta = self.client.post(reverse("viagens_roteiros:novo"), invalido)
        self.assertEqual(resposta.status_code, 200)
        criados = Roteiro.objects.count()

        destino = re.search(
            r'<form method="post" action="([^"]*)" id="form-roteiro"',
            resposta.content.decode(),
        ).group(1)
        self.assertTrue(destino, "o formulário precisa apontar para o roteiro gravado")

        corrigido = dict(invalido, **{"trechos-0-chegada_hora": "18:00"})
        self.client.post(destino, corrigido)
        self.assertEqual(Roteiro.objects.count(), criados)

    def test_dois_trechos_na_mesma_ordem_nao_derrubam_a_gravacao(self):
        # A ordem é reindexada pelo `roteiro-editor.js`, mas ela chega ao
        # servidor em campo oculto do POST: um envio com duas linhas na mesma
        # posição bate na unicidade de (roteiro, ordem). O que se afirma aqui é
        # que isso volta como erro de formulário, e não como erro 500.
        dados = {
            "origem_municipio": self.curitiba.pk,
            "quantidade_servidores": 1,
            "observacoes": "",
            "destinos-TOTAL_FORMS": "0",
            "destinos-INITIAL_FORMS": "0",
            "destinos-MIN_NUM_FORMS": "0",
            "destinos-MAX_NUM_FORMS": "1000",
            "trechos-TOTAL_FORMS": "2",
            "trechos-INITIAL_FORMS": "0",
            "trechos-MIN_NUM_FORMS": "0",
            "trechos-MAX_NUM_FORMS": "1000",
        }
        for i, (origem, destino) in enumerate(
            [(self.curitiba, self.sao_paulo), (self.sao_paulo, self.curitiba)]
        ):
            dados.update(
                {
                    # As duas na posição 1 — o estado que a reindexação evita.
                    f"trechos-{i}-ordem": "1",
                    f"trechos-{i}-sentido": "IDA",
                    f"trechos-{i}-origem_municipio": origem.pk,
                    f"trechos-{i}-destino_municipio": destino.pk,
                    f"trechos-{i}-saida_data": "2026-08-12",
                    f"trechos-{i}-saida_hora": "08:00",
                    f"trechos-{i}-chegada_data": "2026-08-12",
                    f"trechos-{i}-chegada_hora": "14:00",
                    f"trechos-{i}-distancia_km": "",
                    f"trechos-{i}-duracao_min": "",
                }
            )
        resposta = self.client.post(reverse("viagens_roteiros:novo"), dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertLessEqual(Roteiro.objects.latest("pk").trechos.count(), 1)


class ParidadeComOEditorDeReferenciaTests(BaseTelaRoteiroTestCase):
    """O que a tela ganhou ao espelhar o editor da Central de Viagens.

    Estimativa por trecho, rota gravada com o roteiro (e marcada como
    desatualizada quando o percurso muda), gravação automática do rascunho e
    os tempos do trecho gravados em separado.
    """

    def setUp(self):
        self.client.force_login(self.criar_usuario("paridade", "VIAGENS_OPERADOR"))

    def dados(self, **extras):
        base = {
            "origem_municipio": self.curitiba.pk,
            "destinos-TOTAL_FORMS": "1",
            "destinos-INITIAL_FORMS": "0",
            "destinos-MIN_NUM_FORMS": "0",
            "destinos-MAX_NUM_FORMS": "1000",
            "destinos-0-ordem": "1",
            "destinos-0-municipio": self.sao_paulo.pk,
            "trechos-TOTAL_FORMS": "1",
            "trechos-INITIAL_FORMS": "0",
            "trechos-MIN_NUM_FORMS": "0",
            "trechos-MAX_NUM_FORMS": "1000",
            "trechos-0-ordem": "1",
            "trechos-0-origem_municipio": self.curitiba.pk,
            "trechos-0-destino_municipio": self.sao_paulo.pk,
            "trechos-0-saida_data": "2026-08-12",
            "trechos-0-saida_hora": "08:00",
            "trechos-0-chegada_data": "2026-08-12",
            "trechos-0-chegada_hora": "18:00",
            "trechos-0-distancia_km": "",
        }
        base.update(extras)
        return base

    def rota_valida(self):
        from .services.rota import assinatura_dos_ids

        return {
            "rota_geojson": '{"type": "LineString", "coordinates": [[-49.27, -25.43], [-46.63, -23.55]]}',
            "rota_distancia_km": "812.5",
            "rota_duracao_min": "600",
            "rota_fonte": "openrouteservice",
            "rota_assinatura": assinatura_dos_ids(
                [self.curitiba.pk, self.sao_paulo.pk, self.curitiba.pk]
            ),
            "rota_calculada_em": "2026-08-01T10:00:00-03:00",
        }

    # -- regras de tempo do editor de referência ---------------------------

    def test_arredondamento_a_passos_de_15_minutos(self):
        from .services.rota import arredondar_a_15

        self.assertEqual(arredondar_a_15(65), 60)   # resto 5 cai
        self.assertEqual(arredondar_a_15(66), 75)   # resto 6 sobe
        self.assertEqual(arredondar_a_15(0), 0)

    def test_tempo_adicional_sugerido(self):
        from .services.rota import tempo_adicional_sugerido

        self.assertEqual(tempo_adicional_sugerido(20), 0)     # menos de meia hora
        self.assertEqual(tempo_adicional_sugerido(60), 15)    # piso de 15
        self.assertEqual(tempo_adicional_sugerido(300), 45)   # 1/6 = 50 -> 45

    def test_tempo_de_viagem_calibrado(self):
        from .services.rota import tempo_de_viagem

        # (100 + 12) / 74 h = 90,8 min; com 15% dos 90 min da API dá 90,7,
        # que arredonda para 90.
        self.assertEqual(tempo_de_viagem(100, 90), 90)

    # -- estimativa por trecho ---------------------------------------------

    def test_estimar_trecho_sem_chave_explica_a_configuracao(self):
        from cadastros.models import Municipio

        Municipio.objects.filter(
            pk__in=[self.curitiba.pk, self.sao_paulo.pk]
        ).update(latitude="-25.4290000", longitude="-49.2671000")
        with self.settings(OPENROUTESERVICE_API_KEY=""):
            resposta = self.client.post(
                reverse("viagens_roteiros:estimar_trecho"),
                {"origem": self.curitiba.pk, "destino": self.sao_paulo.pk},
            )
        dados = resposta.json()
        self.assertFalse(dados["ok"])
        self.assertIn("OPENROUTESERVICE_API_KEY", dados["motivo"])

    def test_estimar_trecho_responde_do_cache_sem_consultar_a_api(self):
        from django.core.cache import cache

        chave = f"viagens:estimativa:{self.curitiba.pk}:{self.sao_paulo.pk}"
        cache.set(
            chave,
            {
                "origem": self.curitiba.pk,
                "destino": self.sao_paulo.pk,
                "distancia_km": 410.2,
                "duracao_min": 330,
                "tempo_viagem_min": 345,
                "tempo_adicional_sugerido_min": 60,
                "fonte": "openrouteservice",
            },
            60,
        )
        try:
            with self.settings(OPENROUTESERVICE_API_KEY=""):
                resposta = self.client.post(
                    reverse("viagens_roteiros:estimar_trecho"),
                    {"origem": self.curitiba.pk, "destino": self.sao_paulo.pk},
                )
        finally:
            cache.delete(chave)
        dados = resposta.json()
        self.assertTrue(dados["ok"])
        self.assertEqual(dados["tempo_viagem_min"], 345)
        self.assertEqual(dados["tempo_adicional_sugerido_min"], 60)

    def test_estimar_trecho_sem_os_dois_ids_explica(self):
        resposta = self.client.post(
            reverse("viagens_roteiros:estimar_trecho"), {"origem": self.curitiba.pk}
        )
        self.assertFalse(resposta.json()["ok"])

    # -- rota gravada com o roteiro ----------------------------------------

    def test_a_rota_enviada_pela_tela_e_gravada_como_calculada(self):
        self.client.post(reverse("viagens_roteiros:novo"), self.dados(**self.rota_valida()))
        roteiro = Roteiro.objects.latest("pk")
        self.assertEqual(roteiro.rota_status, Roteiro.RotaStatus.CALCULADA)
        self.assertEqual(roteiro.rota_geojson["type"], "LineString")
        self.assertEqual(roteiro.rota_distancia_km, Decimal("812.50"))
        self.assertEqual(roteiro.rota_duracao_min, 600)
        self.assertEqual(roteiro.rota_fonte, "openrouteservice")
        self.assertIsNotNone(roteiro.rota_calculada_em)

    def test_rota_quebrada_e_ignorada_sem_derrubar_o_salvamento(self):
        dados = self.dados(**self.rota_valida())
        dados["rota_geojson"] = "{isto nao e json"
        resposta = self.client.post(reverse("viagens_roteiros:novo"), dados)
        roteiro = Roteiro.objects.latest("pk")
        self.assertEqual(resposta.status_code, 302)
        self.assertIsNone(roteiro.rota_geojson)
        self.assertEqual(roteiro.rota_status, Roteiro.RotaStatus.PENDENTE)

    def test_mudar_o_percurso_sem_recalcular_marca_a_rota_como_desatualizada(self):
        self.client.post(reverse("viagens_roteiros:novo"), self.dados(**self.rota_valida()))
        roteiro = Roteiro.objects.latest("pk")
        destino = roteiro.destinos.get()
        trecho = roteiro.trechos.get()
        # Troca o destino, mas manda a rota antiga (a tela guarda a última).
        editado = self.dados(
            **self.rota_valida(),
            **{
                "destinos-INITIAL_FORMS": "1",
                "destinos-0-id": destino.pk,
                "destinos-0-municipio": self.abatia.pk,
                "trechos-INITIAL_FORMS": "1",
                "trechos-0-id": trecho.pk,
                "trechos-0-destino_municipio": self.abatia.pk,
            },
        )
        self.client.post(reverse("viagens_roteiros:editar", args=[roteiro.pk]), editado)
        roteiro.refresh_from_db()
        self.assertEqual(roteiro.rota_status, Roteiro.RotaStatus.DESATUALIZADA)
        # A rota continua gravada: desatualizada não é apagada.
        self.assertIsNotNone(roteiro.rota_geojson)

    def test_editar_reabre_com_a_rota_gravada_para_o_mapa(self):
        self.client.post(reverse("viagens_roteiros:novo"), self.dados(**self.rota_valida()))
        roteiro = Roteiro.objects.latest("pk")
        resposta = self.client.get(reverse("viagens_roteiros:editar", args=[roteiro.pk]))
        self.assertContains(resposta, 'id="rota-inicial"')
        self.assertContains(resposta, "LineString")

    # -- tempos do trecho ----------------------------------------------------

    def test_tempo_de_viagem_e_adicional_sao_gravados_em_separado(self):
        self.client.post(
            reverse("viagens_roteiros:novo"),
            self.dados(
                **{
                    "trechos-0-tempo_viagem_min": "345",
                    "trechos-0-tempo_adicional_min": "60",
                    "trechos-0-duracao_min": "405",
                    "trechos-0-rota_fonte": "openrouteservice",
                }
            ),
        )
        trecho = Roteiro.objects.latest("pk").trechos.get()
        self.assertEqual(trecho.tempo_viagem_min, 345)
        self.assertEqual(trecho.tempo_adicional_min, 60)
        self.assertEqual(trecho.duracao_min, 405)
        self.assertEqual(trecho.rota_fonte, "openrouteservice")

    def test_trecho_sem_adicional_informado_grava_zero(self):
        self.client.post(reverse("viagens_roteiros:novo"), self.dados())
        trecho = Roteiro.objects.latest("pk").trechos.get()
        self.assertEqual(trecho.tempo_adicional_min, 0)

    # -- gravação automática -------------------------------------------------

    def test_autosave_cria_o_rascunho_e_devolve_os_ids(self):
        antes = Roteiro.objects.count()
        resposta = self.client.post(reverse("viagens_roteiros:autosave_novo"), self.dados())
        dados = resposta.json()
        self.assertTrue(dados["ok"])
        self.assertTrue(dados["criado"])
        self.assertEqual(Roteiro.objects.count(), antes + 1)
        roteiro = Roteiro.objects.get(pk=dados["pk"])
        self.assertEqual(roteiro.status, Roteiro.Status.RASCUNHO)
        self.assertEqual(dados["url_editar"], reverse("viagens_roteiros:editar", args=[roteiro.pk]))
        self.assertEqual(dados["ids"]["destinos-0-id"], roteiro.destinos.get().pk)
        self.assertEqual(dados["ids"]["trechos-0-id"], roteiro.trechos.get().pk)

    def test_autosave_seguinte_edita_o_mesmo_roteiro(self):
        primeiro = self.client.post(
            reverse("viagens_roteiros:autosave_novo"), self.dados()
        ).json()
        ids = primeiro["ids"]
        segundo = self.client.post(
            primeiro["url_autosave"],
            self.dados(
                **{
                    "destinos-INITIAL_FORMS": "1",
                    "destinos-0-id": ids["destinos-0-id"],
                    "trechos-INITIAL_FORMS": "1",
                    "trechos-0-id": ids["trechos-0-id"],
                    "trechos-0-saida_hora": "09:00",
                }
            ),
        ).json()
        self.assertTrue(segundo["ok"])
        self.assertFalse(segundo["criado"])
        roteiro = Roteiro.objects.get(pk=primeiro["pk"])
        self.assertEqual(roteiro.trechos.count(), 1)
        self.assertEqual(roteiro.destinos.count(), 1)
        self.assertEqual(
            timezone.localtime(roteiro.trechos.get().saida_dt).strftime("%H:%M"), "09:00"
        )

    def test_autosave_nao_mexe_em_roteiro_finalizado(self):
        self.client.post(reverse("viagens_roteiros:novo"), self.dados(acao="salvar"))
        roteiro = Roteiro.objects.latest("pk")
        self.assertEqual(roteiro.status, Roteiro.Status.FINALIZADO)
        resposta = self.client.post(
            reverse("viagens_roteiros:autosave", args=[roteiro.pk]),
            self.dados(**{"trechos-0-saida_hora": "05:00"}),
        )
        self.assertFalse(resposta.json()["ok"])
        roteiro.refresh_from_db()
        self.assertEqual(roteiro.status, Roteiro.Status.FINALIZADO)

    def test_autosave_exige_permissao_de_edicao(self):
        from django.contrib.auth import get_user_model

        leitora = get_user_model().objects.create_user("leitora_autosave")
        leitora.setores.add(self.setor)
        self.client.force_login(leitora)
        resposta = self.client.post(reverse("viagens_roteiros:autosave_novo"), self.dados())
        self.assertEqual(resposta.status_code, 403)

    # -- o que a tela carrega ------------------------------------------------

    def test_a_tela_traz_os_enderecos_e_liga_a_gravacao_automatica(self):
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        self.assertContains(resposta, 'data-url-estimar="')
        self.assertContains(resposta, 'data-url-autosave="')
        self.assertContains(resposta, 'data-autosave="1"')
        self.assertContains(resposta, 'name="rota_geojson"')

    def test_roteiro_finalizado_abre_com_a_gravacao_automatica_desligada(self):
        self.client.post(reverse("viagens_roteiros:novo"), self.dados(acao="salvar"))
        roteiro = Roteiro.objects.latest("pk")
        resposta = self.client.get(reverse("viagens_roteiros:editar", args=[roteiro.pk]))
        self.assertContains(resposta, 'data-autosave="0"')

    def test_o_calendario_dos_trechos_e_sequencial_e_o_do_bate_volta_tambem(self):
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        html = resposta.content.decode()
        self.assertIn('id="datas-trechos" data-custom-date-multi', html)
        self.assertEqual(html.count("data-sequencial"), 2)
        self.assertIn("data-custom-date-multi-undo", html)

    def test_a_tela_mostra_a_situacao_da_rota_e_o_aviso_de_desatualizada(self):
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        self.assertContains(resposta, "data-rota-status")
        self.assertContains(resposta, "data-rota-desatualizada")
        self.assertContains(resposta, "Recalcule a rota")

    # -- defeitos vistos ao gravar de verdade ------------------------------

    def test_id_de_trecho_ja_apagado_nao_derruba_a_gravacao_seguinte(self):
        # A tela guarda oculta a linha que o autosave anterior apagou, ainda
        # com o id antigo e marcada para exclusão. Para o formset esse id é
        # "escolha inválida", e a gravação inteira falhava por causa dela.
        primeiro = self.client.post(
            reverse("viagens_roteiros:autosave_novo"), self.dados()
        ).json()
        trecho_antigo = primeiro["ids"]["trechos-0-id"]
        # Apaga o trecho 0 e cria outro no lugar (índice 1).
        segundo = self.client.post(
            primeiro["url_autosave"],
            self.dados(
                **{
                    "destinos-INITIAL_FORMS": "1",
                    "destinos-0-id": primeiro["ids"]["destinos-0-id"],
                    "trechos-TOTAL_FORMS": "2",
                    "trechos-INITIAL_FORMS": "1",
                    "trechos-0-id": trecho_antigo,
                    "trechos-0-DELETE": "on",
                    "trechos-1-ordem": "1",
                    "trechos-1-origem_municipio": self.curitiba.pk,
                    "trechos-1-destino_municipio": self.sao_paulo.pk,
                    "trechos-1-saida_data": "2026-08-13",
                    "trechos-1-saida_hora": "08:00",
                    "trechos-1-chegada_data": "2026-08-13",
                    "trechos-1-chegada_hora": "18:00",
                }
            ),
        ).json()
        self.assertTrue(segundo["gravou"]["trechos"])
        self.assertNotIn("trechos-0-id", segundo["ids"])
        # Terceira gravação ainda carrega o id apagado, oculto e marcado.
        terceiro = self.client.post(
            primeiro["url_autosave"],
            self.dados(
                **{
                    "destinos-INITIAL_FORMS": "1",
                    "destinos-0-id": primeiro["ids"]["destinos-0-id"],
                    "trechos-TOTAL_FORMS": "2",
                    "trechos-INITIAL_FORMS": "2",
                    "trechos-0-id": trecho_antigo,
                    "trechos-0-DELETE": "on",
                    "trechos-1-id": segundo["ids"]["trechos-1-id"],
                    "trechos-1-ordem": "1",
                    "trechos-1-origem_municipio": self.curitiba.pk,
                    "trechos-1-destino_municipio": self.sao_paulo.pk,
                    "trechos-1-saida_data": "2026-08-13",
                    "trechos-1-saida_hora": "10:00",
                    "trechos-1-chegada_data": "2026-08-13",
                    "trechos-1-chegada_hora": "18:00",
                }
            ),
        ).json()
        self.assertTrue(terceiro["gravou"]["trechos"], terceiro)
        roteiro = Roteiro.objects.get(pk=primeiro["pk"])
        self.assertEqual(roteiro.trechos.count(), 1)
        self.assertEqual(
            timezone.localtime(roteiro.trechos.get().saida_dt).strftime("%H:%M"), "10:00"
        )

    def test_salvar_tambem_tolera_id_apagado(self):
        primeiro = self.client.post(
            reverse("viagens_roteiros:autosave_novo"), self.dados()
        ).json()
        trecho_antigo = primeiro["ids"]["trechos-0-id"]
        RoteiroTrecho.objects.filter(pk=trecho_antigo).delete()
        resposta = self.client.post(
            primeiro["url_editar"],
            self.dados(
                acao="salvar",
                **{
                    "destinos-INITIAL_FORMS": "1",
                    "destinos-0-id": primeiro["ids"]["destinos-0-id"],
                    "trechos-INITIAL_FORMS": "1",
                    "trechos-0-id": trecho_antigo,
                },
            ),
        )
        self.assertRedirects(resposta, reverse("viagens_roteiros:lista"))
        self.assertEqual(Roteiro.objects.get(pk=primeiro["pk"]).trechos.count(), 1)

    def test_editar_reabre_as_datas_dos_trechos_em_iso(self):
        # `<input type="date">` só entende ISO: a data localizada ("12 de
        # Agosto de 2026") reabria o campo em branco.
        self.client.post(reverse("viagens_roteiros:novo"), self.dados())
        roteiro = Roteiro.objects.latest("pk")
        resposta = self.client.get(reverse("viagens_roteiros:editar", args=[roteiro.pk]))
        self.assertContains(resposta, 'value="2026-08-12"')
        self.assertContains(resposta, 'value="08:00"')
        self.assertContains(resposta, 'value="18:00"')

    def test_autosave_avisa_quando_os_trechos_nao_passam(self):
        resposta = self.client.post(
            reverse("viagens_roteiros:autosave_novo"),
            self.dados(**{"trechos-0-chegada_hora": "06:00"}),
        ).json()
        self.assertTrue(resposta["ok"])
        self.assertFalse(resposta["gravou"]["trechos"])
        self.assertIn("trechos", resposta["motivo"])

    def test_previa_funciona_na_edicao_com_os_ids_dos_trechos(self):
        # Na edição o formulário carrega os ids gravados; a prévia, que roda
        # sem roteiro, tratava esse id como escolha inválida e não calculava.
        self.client.post(reverse("viagens_roteiros:novo"), self.dados())
        roteiro = Roteiro.objects.latest("pk")
        resposta = self.client.post(
            reverse("viagens_roteiros:previa_diarias"),
            self.dados(
                **{
                    "destinos-INITIAL_FORMS": "1",
                    "destinos-0-id": roteiro.destinos.get().pk,
                    "trechos-INITIAL_FORMS": "1",
                    "trechos-0-id": roteiro.trechos.get().pk,
                }
            ),
        )
        dados = resposta.json()
        self.assertTrue(dados["ok"], dados)
        # Capital, saída e chegada no mesmo dia: 30% de R$ 371,26.
        self.assertEqual(dados["totais"]["total_valor"], "111,38")

    def test_editar_reabre_os_numeros_do_trecho_sem_localizar(self):
        # "257,88" no campo oculto era recusado pelo próprio formulário ao
        # salvar de novo, e a prévia deixava o trecho de fora da conta.
        self.client.post(
            reverse("viagens_roteiros:novo"),
            self.dados(
                **{
                    "trechos-0-distancia_km": "257.88",
                    "trechos-0-tempo_viagem_min": "1230",
                    "trechos-0-duracao_min": "1260",
                }
            ),
        )
        roteiro = Roteiro.objects.latest("pk")
        html = self.client.get(
            reverse("viagens_roteiros:editar", args=[roteiro.pk])
        ).content.decode()
        self.assertIn('value="257.88"', html)
        self.assertIn('value="1230"', html)
        self.assertNotIn('value="257,88"', html)
        self.assertNotIn('value="1.230"', html)
        # E o reenvio do que a tela carregou salva sem erro.
        resposta = self.client.post(
            reverse("viagens_roteiros:editar", args=[roteiro.pk]),
            self.dados(
                acao="salvar",
                **{
                    "destinos-INITIAL_FORMS": "1",
                    "destinos-0-id": roteiro.destinos.get().pk,
                    "trechos-INITIAL_FORMS": "1",
                    "trechos-0-id": roteiro.trechos.get().pk,
                    "trechos-0-distancia_km": "257.88",
                },
            ),
        )
        self.assertRedirects(resposta, reverse("viagens_roteiros:lista"))


class SemTelaDeDetalheTests(BaseTelaRoteiroTestCase):
    """O roteiro tem uma tela só — a de edição, que também mostra o cálculo.

    Decisão do dono do produto (02/09/2026): a tela de detalhe repetia o que
    o editor já mostra e obrigava a um pulo a mais para qualquer ajuste.
    """

    def setUp(self):
        self.client.force_login(self.criar_usuario("sem_detalhe", "VIAGENS_OPERADOR"))

    def test_o_endereco_antigo_leva_a_edicao(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        resposta = self.client.get(f"/viagens/roteiros/{roteiro.pk}/")
        self.assertRedirects(
            resposta,
            reverse("viagens_roteiros:editar", args=[roteiro.pk]),
            status_code=301,
        )

    def test_a_lista_abre_o_roteiro_na_edicao(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        resposta = self.client.get(reverse("viagens_roteiros:lista"))
        self.assertContains(
            resposta, reverse("viagens_roteiros:editar", args=[roteiro.pk])
        )

    def test_a_edicao_traz_as_acoes_do_ciclo_de_vida(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        resposta = self.client.get(reverse("viagens_roteiros:editar", args=[roteiro.pk]))
        for nome in ("calcular", "cancelar", "excluir"):
            self.assertContains(
                resposta, reverse(f"viagens_roteiros:{nome}", args=[roteiro.pk])
            )
        self.assertContains(resposta, "Situação do roteiro")

    def test_a_situacao_do_roteiro_aparece_no_cabecalho(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        resposta = self.client.get(reverse("viagens_roteiros:editar", args=[roteiro.pk]))
        self.assertContains(resposta, "editor-roteiro__titulo")
        self.assertContains(resposta, "Rascunho")
        roteiro.cancelar("Evento adiado")
        resposta = self.client.get(reverse("viagens_roteiros:editar", args=[roteiro.pk]))
        self.assertContains(resposta, "status-badge--cancelada")

    def test_roteiro_novo_nao_oferece_cancelar_nem_excluir(self):
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        self.assertNotContains(resposta, "Situação do roteiro")

    def test_cancelar_volta_para_a_edicao_e_a_tela_mostra_o_motivo(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        resposta = self.client.post(
            reverse("viagens_roteiros:cancelar", args=[roteiro.pk]),
            {"motivo": "Evento adiado"},
            follow=True,
        )
        self.assertRedirects(
            resposta, reverse("viagens_roteiros:editar", args=[roteiro.pk])
        )
        self.assertContains(resposta, "Evento adiado")
        self.assertContains(resposta, "Reativar")

    def test_calcular_volta_para_a_edicao(self):
        roteiro = self.roteiro_curitiba_sp_abatia()
        resposta = self.client.post(
            reverse("viagens_roteiros:calcular", args=[roteiro.pk])
        )
        self.assertRedirects(
            resposta, reverse("viagens_roteiros:editar", args=[roteiro.pk])
        )


class NumeracaoDasLinhasNovasTests(BaseTelaRoteiroTestCase):
    """A linha em branco não nasce na posição de outra.

    `ordem` tem `default=1`: sem numeração, o slot em branco chegava ao
    servidor disputando a posição 1 com o primeiro trecho de verdade. A tela
    reindexa por JavaScript, mas o formulário não pode depender disso.
    Encontrado pela auditoria comparativa com o sistema de origem.
    """

    def setUp(self):
        self.client.force_login(self.criar_usuario("numeracao", "VIAGENS_OPERADOR"))

    def ordens(self, resposta, prefixo):
        return re.findall(
            r'name="%s-\d+-ordem"[^>]*value="(\d+)"' % prefixo,
            resposta.content.decode(),
        )

    def test_a_tela_nova_numera_o_slot_em_branco_a_partir_de_um(self):
        resposta = self.client.get(reverse("viagens_roteiros:novo"))
        self.assertEqual(self.ordens(resposta, "trechos"), ["1"])
        self.assertEqual(self.ordens(resposta, "destinos"), ["1"])

    def test_a_edicao_numera_a_partir_dos_trechos_gravados(self):
        roteiro = self.roteiro_curitiba_sp_abatia()  # 3 trechos gravados
        resposta = self.client.get(reverse("viagens_roteiros:editar", args=[roteiro.pk]))
        ordens = self.ordens(resposta, "trechos")
        # Os gravados mantêm a posição que têm; o slot em branco vem depois.
        self.assertEqual(ordens, ["1", "2", "3", "4"])
