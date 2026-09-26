"""Conflitos de agenda (m011, m049, m067): o serviço central e as telas."""

from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Estado, Municipio, OrgaoResponsavel, Regiao, TipoEvento, UnidadeMovel
from core import conflitos as servico
from demandas_eventos.models import DemandaEvento, Palestrante, StatusDemanda
from solicitacoes.models import SolicitacaoEvento, StatusSolicitacao
from viagens_cadastros.models import Servidor, Unidade, Viatura
from viagens_oficios.models import Oficio
from viagens_roteiros.models import Roteiro, RoteiroDestino, RoteiroTrecho


def quando(dia, hora, minuto=0):
    return timezone.make_aware(datetime(2026, 10, dia, hora, minuto))


class BaseConflitos(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pr = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        regiao = Regiao.objects.create(nome="Região Conflitos")
        cls.curitiba = Municipio.objects.create(nome="Curitiba Teste", estado=cls.pr, regiao=regiao)
        cls.londrina = Municipio.objects.create(nome="Londrina Teste", estado=cls.pr, regiao=regiao)
        # Unidades diferentes: o cruzamento não olha a unidade de ninguém.
        cls.ana = Servidor.objects.create(nome="ANA CONFLITO", unidade=Unidade.objects.create(nome="Unidade A"))
        cls.bia = Servidor.objects.create(nome="BIA CONFLITO", unidade=Unidade.objects.create(nome="Unidade B"))
        cls.viatura = Viatura.objects.create(placa="AAA1B23", modelo="VIATURA TESTE")
        cls.um = UnidadeMovel.objects.create(nome="Unidade Móvel 02")
        cls.tipo = TipoEvento.objects.create(nome="Ação conflito")
        cls.orgao = OrgaoResponsavel.objects.create(nome="Órgão conflito")
        cls.user = get_user_model().objects.create_superuser("root_conflitos", password="x")

    def oficio(self, saida, chegada, *, servidores=(), motorista=None, viatura=None, destino=None, **campos):
        roteiro = Roteiro.objects.create(origem_municipio=self.curitiba, saida_dt=saida, retorno_chegada_dt=chegada)
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=destino or self.londrina)
        oficio = Oficio.objects.create(roteiro=roteiro, motorista=motorista, viatura=viatura, **campos)
        oficio.servidores.set(servidores)
        return oficio

    def solicitacao(self, inicio, fim=None, **campos):
        dados = {
            "data_inicio_evento": inicio, "data_fim_evento": fim, "municipio": self.londrina,
            "tipo_evento": self.tipo, "orgao_responsavel": self.orgao, "criado_por": self.user,
            "status": StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
        }
        dados.update(campos)
        return SolicitacaoEvento.objects.create(**dados)

    def buscar(self, inicio, fim, **kwargs):
        return servico.conflitos(servico.consulta(inicio, fim, **kwargs))


class ServicoConflitosTests(BaseConflitos):
    def test_horarios_encostados_nao_conflitam(self):
        # Chega a Curitiba às 17:30; outro ofício sai às 17:31 com a mesma pessoa e viatura.
        self.oficio(quando(12, 8), quando(12, 17, 30), servidores=[self.ana], viatura=self.viatura, numero=12, ano=2026)
        self.assertEqual(self.buscar(quando(12, 17, 31), quando(13, 10), servidores=[self.ana], viaturas=[self.viatura]), [])
        self.assertEqual(self.buscar(quando(12, 17, 30), quando(13, 10), servidores=[self.ana]), [])

    def test_sobreposicao_real_gera_aviso_com_horario_e_local(self):
        self.oficio(quando(12, 8), quando(12, 17, 30), servidores=[self.ana], viatura=self.viatura, numero=12, ano=2026)
        achados = self.buscar(quando(12, 17), quando(12, 20), servidores=[self.ana], viaturas=[self.viatura])
        mensagens = [c.mensagem for c in achados]
        self.assertIn("ANA CONFLITO já está no Ofício 12/2026 de 12/10 08:00 a 12/10 17:30 (Londrina Teste)", mensagens)
        self.assertTrue(any(m.startswith("Viatura AAA1B23 já está no Ofício 12/2026") for m in mensagens))
        self.assertTrue(all(c.url.endswith(f"/editar/") for c in achados))

    def test_motorista_e_equipe_sao_a_mesma_pessoa(self):
        self.oficio(quando(12, 8), quando(12, 18), motorista=self.bia, numero=3, ano=2026)
        achados = self.buscar(quando(12, 9), quando(12, 10), servidores=[self.bia])
        self.assertEqual(len(achados), 1)
        self.assertIn("como motorista", achados[0].mensagem)

    def test_cancelado_e_o_proprio_registro_nao_contam(self):
        cancelado = self.oficio(quando(12, 8), quando(12, 18), servidores=[self.ana], cancelado=True)
        proprio = self.oficio(quando(12, 8), quando(12, 18), servidores=[self.ana])
        consulta = servico.consulta(quando(12, 9), quando(12, 10), servidores=[self.ana], excluir={"oficio": {proprio.pk}})
        self.assertEqual(servico.conflitos(consulta), [])
        self.assertTrue(cancelado.cancelado)

    def test_periodo_so_nos_trechos(self):
        roteiro = Roteiro.objects.create(origem_municipio=self.curitiba)
        RoteiroTrecho.objects.create(roteiro=roteiro, ordem=1, saida_dt=quando(20, 6), chegada_dt=quando(20, 10))
        RoteiroTrecho.objects.create(roteiro=roteiro, ordem=2, saida_dt=quando(21, 14), chegada_dt=quando(21, 18),
                                     sentido=RoteiroTrecho.Sentido.RETORNO)
        Roteiro.objects.filter(pk=roteiro.pk).update(saida_dt=None, retorno_chegada_dt=None, retorno_saida_dt=None, chegada_dt=None)
        oficio = Oficio.objects.create(roteiro=roteiro)
        oficio.servidores.add(self.ana)
        self.assertEqual(len(self.buscar(quando(21, 12), quando(21, 13), servidores=[self.ana])), 1)
        self.assertEqual(self.buscar(quando(21, 18), quando(21, 19), servidores=[self.ana]), [])

    def test_solicitacao_deferida_ocupa_unidade_movel_e_motorista_o_dia_inteiro(self):
        self.solicitacao(date(2026, 10, 10), date(2026, 10, 12), unidade_movel_designada=self.um, motorista=self.ana)
        self.solicitacao(date(2026, 10, 10), status=StatusSolicitacao.AGUARDANDO_DESPACHO, unidade_movel_designada=self.um)
        self.solicitacao(date(2026, 10, 10), status=StatusSolicitacao.CANCELADA, unidade_movel_designada=self.um)
        achados = self.buscar(quando(12, 20), quando(13, 8), unidades_moveis=[self.um], servidores=[self.ana])
        self.assertEqual({c.tipo for c in achados}, {"unidade_movel", "servidor"})
        self.assertIn("Unidade móvel Unidade Móvel 02 já está na Solicitação", achados[0].mensagem + achados[1].mensagem)
        self.assertIn("10/10 a 12/10/2026", achados[0].mensagem)
        # No dia seguinte ao último, livre.
        self.assertEqual(self.buscar(quando(13, 0), quando(13, 8), unidades_moveis=[self.um]), [])

    def test_ofício_e_solicitacao_se_cruzam(self):
        # Motorista designado num evento deferido não pode ir num ofício no mesmo dia (e vice-versa).
        self.solicitacao(date(2026, 10, 12), motorista=self.bia)
        oficio = self.oficio(quando(12, 8), quando(12, 12), motorista=self.bia)
        self.assertEqual([c.documento for c in servico.conflitos_do_oficio(oficio)][:1], ["Solicitação #%d" % SolicitacaoEvento.objects.get().pk])
        s = self.solicitacao(date(2026, 10, 12), motorista=self.bia)
        self.assertTrue(any(c.documento.startswith("Ofício") for c in servico.conflitos_da_solicitacao(s)))

    def test_pedido_repetido_mesmo_municipio_e_data(self):
        outra = self.solicitacao(date(2026, 10, 11), status=StatusSolicitacao.AGUARDANDO_DESPACHO)
        self.solicitacao(date(2026, 10, 11), status=StatusSolicitacao.RASCUNHO)
        nova = SolicitacaoEvento(data_inicio_evento=date(2026, 10, 10), data_fim_evento=date(2026, 10, 12), municipio=self.londrina)
        achados = servico.conflitos_da_solicitacao(nova)
        self.assertEqual([c.documento for c in achados], [f"Solicitação #{outra.pk}"])
        self.assertTrue(achados[0].mensagem.startswith(f"Já existe pedido na Solicitação #{outra.pk}"))
        self.assertEqual(servico.conflitos_da_solicitacao(outra), [])

    def test_palestrante_na_mesma_data(self):
        palestrante = Palestrante.objects.create(nome="PALESTRANTE X")
        outra = DemandaEvento.objects.create(data_solicitacao=date(2026, 9, 1), solicitante="Escola", data_inicio_evento=date(2026, 10, 15))
        outra.palestrantes.add(palestrante)
        cancelada = DemandaEvento.objects.create(data_solicitacao=date(2026, 9, 1), solicitante="Escola", data_inicio_evento=date(2026, 10, 15),
                                                 status=StatusDemanda.CANCELADA)
        cancelada.palestrantes.add(palestrante)
        nova = DemandaEvento(data_solicitacao=date(2026, 9, 1), data_inicio_evento=date(2026, 10, 15))
        achados = servico.conflitos_da_demanda(nova, palestrantes=[palestrante.pk])
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0].mensagem, f"PALESTRANTE X já está na Palestra #{outra.pk} em 15/10/2026")

    def test_fonte_registravel(self):
        chamadas = []

        @servico.registrar_fonte("teste_extrajornada")
        def _fonte(consulta):
            chamadas.append(consulta)
            return [servico.Conflito(tipo="servidor", recurso="ANA", no_documento="na Extrajornada #1",
                                     documento="Extrajornada #1", inicio=quando(1, 8), fim=quando(1, 12), chave=("x", 1))]

        self.addCleanup(servico._FONTES.pop, "teste_extrajornada")
        self.assertEqual(len(self.buscar(quando(1, 11), quando(1, 13), servidores=[self.ana])), 1)
        self.assertEqual(self.buscar(quando(1, 12), quando(1, 13), servidores=[self.ana]), [])
        self.assertEqual(len(chamadas), 2)

    def test_endpoint_json(self):
        oficio = self.oficio(quando(12, 8), quando(12, 17, 30), servidores=[self.ana], numero=12, ano=2026)
        self.client.force_login(self.user)
        url = reverse("core:conflitos")
        resposta = self.client.get(url, {"inicio": "2026-10-12T09:00", "fim": "2026-10-12T10:00", "servidores": [self.ana.pk]})
        self.assertEqual(len(resposta.json()["conflitos"]), 1)
        # O próprio ofício, pelo período do roteiro, não conflita consigo.
        resposta = self.client.get(url, {"oficio": oficio.pk, "servidores": [self.ana.pk]})
        self.assertEqual(resposta.json()["conflitos"], [])
        resposta = self.client.get(url, {"inicio": "2026-10-12", "servidores": [self.ana.pk]})
        self.assertEqual(len(resposta.json()["conflitos"]), 1)
        self.assertEqual(self.client.get(url).json()["conflitos"], [])
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)


class TelasConflitosTests(BaseConflitos):
    def test_solicitacao_mostra_aviso_no_formulario(self):
        self.solicitacao(date(2026, 10, 10), unidade_movel_designada=self.um)
        s = self.solicitacao(date(2026, 10, 10), status=StatusSolicitacao.AGUARDANDO_DESPACHO, unidade_movel=True,
                             unidade_movel_designada=self.um)
        self.client.force_login(self.user)
        conteudo = self.client.get(reverse("solicitacoes:editar", args=[s.pk])).content.decode()
        self.assertIn("Conflito de agenda", conteudo)
        self.assertIn("Unidade móvel Unidade Móvel 02 já está na Solicitação", conteudo)

    def test_palestra_mostra_aviso(self):
        palestrante = Palestrante.objects.create(nome="PALESTRANTE Y")
        outra = DemandaEvento.objects.create(data_solicitacao=date(2026, 9, 1), solicitante="Escola", data_inicio_evento=date(2026, 10, 15))
        outra.palestrantes.add(palestrante)
        demanda = DemandaEvento.objects.create(data_solicitacao=date(2026, 9, 1), solicitante="Clube", data_inicio_evento=date(2026, 10, 15))
        demanda.palestrantes.add(palestrante)
        self.client.force_login(self.user)
        conteudo = self.client.get(reverse("demandas_eventos:editar", args=[demanda.pk])).content.decode()
        self.assertIn(f"PALESTRANTE Y já está na Palestra #{outra.pk}", conteudo)
