"""Planejamento semiautomático: o que as viagens feitas ensinam à viagem nova."""
from datetime import date, datetime, timedelta

from django.urls import reverse
from django.utils import timezone

from viagens_cadastros.models import Servidor, Viatura
from viagens_oficios.models import Justificativa, ModeloJustificativa, Oficio
from viagens_roteiros.models import Roteiro, RoteiroDestino, RoteiroTrecho
from viagens_viagem.planejamento import completar_oficio, planejar_horarios, sugestoes_de_equipe

from .fixtures import CenarioViagem


def _quando(dia, hora, minuto=0):
    return timezone.make_aware(datetime.combine(dia, datetime.min.time()).replace(hour=hora, minute=minuto))


class PlanejamentoTests(CenarioViagem):
    def viagem_feita(self, cidade, inicio, fim, ida, volta, *, tempo=None, cancelada=False, servidores=(), **campos):
        """Uma viagem com ofício (a que alguém revisou) e o roteiro com ida e volta."""
        viagem = self.viagem(destino_municipio=cidade, data_inicio=inicio, data_fim=fim)
        roteiro = Roteiro.objects.create(origem_municipio=self.sede, viagem=viagem)
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=cidade, ordem=1)
        RoteiroTrecho.objects.create(roteiro=roteiro, ordem=1, sentido=RoteiroTrecho.Sentido.IDA, origem_municipio=self.sede,
                                     destino_municipio=cidade, saida_dt=ida, tempo_viagem_min=tempo)
        RoteiroTrecho.objects.create(roteiro=roteiro, ordem=2, sentido=RoteiroTrecho.Sentido.RETORNO, origem_municipio=cidade,
                                     destino_municipio=self.sede, saida_dt=volta)
        oficio = Oficio.objects.create(viagem=viagem, roteiro=roteiro, **campos)
        oficio.servidores.set(servidores)
        if cancelada:
            Oficio.objects.filter(pk=oficio.pk).update(cancelado=True)
        return viagem

    def test_sem_historico_fica_a_regra_de_sempre(self):
        plano = planejar_horarios(self.sede, self.londrina, date(2026, 11, 3), date(2026, 11, 4))
        self.assertEqual(plano.base, "padrao")
        self.assertEqual(timezone.localtime(plano.ida), _quando(date(2026, 11, 3), 8))
        self.assertEqual(timezone.localtime(plano.volta), _quando(date(2026, 11, 4), 16))
        self.assertIn("o horário de sempre", plano.explicacao)

    def test_mesma_cidade_ensina_vespera_e_volta_no_dia_seguinte(self):
        # Para Londrina a equipe sempre sai na véspera às 14:00 e volta no dia seguinte ao fim às 09:00.
        for inicio in (date(2026, 3, 10), date(2026, 5, 12)):
            fim = inicio + timedelta(days=1)
            self.viagem_feita(self.londrina, inicio, fim, _quando(inicio - timedelta(days=1), 14),
                              _quando(fim + timedelta(days=1), 9, 5))
        # Uma fora do padrão não muda a maioria.
        self.viagem_feita(self.londrina, date(2026, 6, 2), date(2026, 6, 2), _quando(date(2026, 6, 2), 6),
                          _quando(date(2026, 6, 2), 18))
        plano = planejar_horarios(self.sede, self.londrina, date(2026, 11, 3), date(2026, 11, 4))
        self.assertEqual(plano.base, "cidade")
        self.assertEqual(plano.amostras, 3)
        self.assertEqual(timezone.localtime(plano.ida), _quando(date(2026, 11, 2), 14))
        self.assertEqual(timezone.localtime(plano.volta), _quando(date(2026, 11, 5), 9))
        self.assertIn("nas 3 viagens a Londrina", plano.explicacao)
        self.assertIn("véspera", plano.explicacao)

    def test_cidade_nova_aprende_com_distancia_parecida(self):
        self.viagem_feita(self.maringa, date(2026, 4, 7), date(2026, 4, 7), _quando(date(2026, 4, 6), 15),
                          _quando(date(2026, 4, 7), 17), tempo=420)
        plano = planejar_horarios(self.sede, self.londrina, date(2026, 11, 3), date(2026, 11, 3), tempo_min=400)
        self.assertEqual(plano.base, "distancia")
        self.assertEqual(timezone.localtime(plano.ida), _quando(date(2026, 11, 2), 15))
        # Tempo de outra faixa: não serve de exemplo.
        self.assertEqual(planejar_horarios(self.sede, self.londrina, date(2026, 11, 3), date(2026, 11, 3), tempo_min=60).base,
                         "padrao")

    def test_oficio_cancelado_nao_ensina(self):
        self.viagem_feita(self.londrina, date(2026, 3, 10), date(2026, 3, 10), _quando(date(2026, 3, 10), 5),
                          _quando(date(2026, 3, 10), 20), cancelada=True)
        self.assertEqual(planejar_horarios(self.sede, self.londrina, date(2026, 11, 3), date(2026, 11, 3)).base, "padrao")

    def test_volta_que_nao_cabe_depois_da_ida_cai_na_regra(self):
        # Viagem de um dia com volta às 07:00: numa viagem nova de 5 h, a volta viria antes da chegada.
        self.viagem_feita(self.londrina, date(2026, 3, 10), date(2026, 3, 10), _quando(date(2026, 3, 10), 6),
                          _quando(date(2026, 3, 10), 7))
        plano = planejar_horarios(self.sede, self.londrina, date(2026, 11, 3), date(2026, 11, 3), tempo_min=300)
        self.assertEqual(plano.base, "padrao")

    def test_equipe_sugerida_pela_mesma_cidade_ou_tipo(self):
        vtr = Viatura.objects.create(placa="QWE1R23", modelo="VTR FREQUENTE")
        self.viagem_feita(self.londrina, date(2026, 3, 10), date(2026, 3, 10), _quando(date(2026, 3, 10), 8),
                          _quando(date(2026, 3, 10), 16), servidores=[self.b], viatura=vtr, motorista=self.b)
        nova = self.viagem(data_inicio=date(2026, 11, 3), data_fim=date(2026, 11, 3))
        sugestoes = sugestoes_de_equipe(nova)
        self.assertEqual(sugestoes.viagens, 1)
        self.assertEqual(sugestoes.servidores[self.b.pk], 2)  # mesma cidade conta em dobro
        self.assertEqual(sugestoes.viaturas[vtr.pk], 2)
        self.assertEqual(sugestoes.servidores[self.a.pk], 0)

    def test_completa_custeio_e_justificativa_pelo_historico(self):
        for inicio in (date(2026, 3, 10), date(2026, 5, 12)):
            self.viagem_feita(self.londrina, inicio, inicio, _quando(inicio, 8), _quando(inicio, 16),
                              custeio=Oficio.CUSTEIO_OUTRA_INSTITUICAO, custeio_observacao="Prefeitura de Londrina")
        ModeloJustificativa.objects.create(nome="Prazo curto", texto="Viagem a {destino} com {dias_antecedencia} dias.",
                                           is_padrao=True)
        # A saída em 3 dias: o prazo (10 dias) exige justificativa.
        saida = timezone.localdate() + timedelta(days=3)
        viagem = self.viagem(data_inicio=saida, data_fim=saida)
        roteiro = Roteiro.objects.create(origem_municipio=self.sede, viagem=viagem, saida_dt=_quando(saida, 8))
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.londrina, ordem=1)
        oficio = Oficio.objects.create(viagem=viagem, roteiro=roteiro, motivo="Atividade")
        feito = completar_oficio(oficio)
        oficio.refresh_from_db()
        self.assertEqual(oficio.custeio, Oficio.CUSTEIO_OUTRA_INSTITUICAO)
        self.assertEqual(oficio.custeio_observacao, "Prefeitura de Londrina")
        justificativa = Justificativa.objects.get(oficio=oficio)
        self.assertEqual(justificativa.modelo.nome, "PRAZO CURTO")
        self.assertIn("LONDRINA/PR", justificativa.texto)
        self.assertIn("3 dias", justificativa.texto)
        self.assertEqual(justificativa.status, Justificativa.STATUS_RASCUNHO)
        self.assertEqual(len(feito), 2)

    def test_custeio_sem_concordancia_nao_muda(self):
        self.viagem_feita(self.londrina, date(2026, 3, 10), date(2026, 3, 10), _quando(date(2026, 3, 10), 8),
                          _quando(date(2026, 3, 10), 16), custeio=Oficio.CUSTEIO_OUTRA_INSTITUICAO)
        viagem = self.viagem()
        oficio = Oficio.objects.create(viagem=viagem, motivo="Atividade")
        completar_oficio(oficio)
        oficio.refresh_from_db()
        self.assertEqual(oficio.custeio, Oficio.CUSTEIO_UNIDADE_DPC)


class TelaSoFaltaEquipeTests(CenarioViagem):
    def setUp(self):
        super().setUp()
        self.v = self.viagem()
        Roteiro.objects.create(origem_municipio=self.sede, viagem=self.v)
        self.url = reverse("viagens_viagem:gerar_documentos", args=[self.v.pk])

    def test_painel_leva_direto_a_equipe(self):
        r = self.client.get(self.etapa(self.v, 1))
        self.assertContains(r, "Só falta a equipe")
        self.assertContains(r, "Escolher equipe e viatura")

    def test_quem_costuma_ir_vem_primeiro(self):
        zeca = Servidor.objects.create(nome="ZECA FREQUENTE", cargo=self.cargo, unidade=self.unidade, cpf="10120230340")
        antiga = self.viagem(data_inicio=date(2026, 2, 3), data_fim=date(2026, 2, 3))
        oficio = Oficio.objects.create(viagem=antiga)
        oficio.servidores.set([zeca])
        r = self.client.get(self.url)
        self.assertContains(r, "Planejado pelo histórico")
        html = r.content.decode()
        self.assertLess(html.index("ZECA FREQUENTE"), html.index("ANA VIAGEM"))
        self.assertIn("costuma ir em viagens assim", html)

    def test_gerar_avisa_o_que_o_historico_preencheu(self):
        ModeloJustificativa.objects.create(nome="Prazo", texto="Justificativa de {destino}.", is_padrao=True)
        saida = timezone.localdate() + timedelta(days=2)
        roteiro = self.v.roteiros.get()
        roteiro.saida_dt = _quando(saida, 8)
        roteiro.save()
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.londrina, ordem=1)
        r = self.client.post(self.url, {"quantidade_oficios": "1", "acao": "gerar", "oficio-0-servidores": [str(self.a.pk)],
                                        "oficio-0-viatura": str(self.viatura.pk)}, follow=True)
        self.assertContains(r, "Preenchido pelo histórico")
        oficio = Oficio.objects.get(viagem=self.v)
        self.assertTrue(Justificativa.objects.get(oficio=oficio).texto.startswith("Justificativa de"))
        self.assertNotContains(self.client.get(self.etapa(self.v, 1)), "Só falta a equipe")
