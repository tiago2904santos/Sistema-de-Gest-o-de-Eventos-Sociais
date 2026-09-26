"""Painel "o que fazer hoje": a próxima ação de cada OS (m028)."""

import datetime as dt
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from . import services
from .models import AcaoHistoricoCoffeeBreak, HistoricoCoffeeBreak
from .tests import BaseCoffeeBreakTestCase

HOJE = dt.date(2026, 9, 26)


def _criada_em(solicitacao, dia):
    from .models import SolicitacaoCoffeeBreak

    SolicitacaoCoffeeBreak.objects.filter(pk=solicitacao.pk).update(
        criado_em=timezone.make_aware(dt.datetime.combine(dia, dt.time(10)))
    )


class ProximaAcaoTests(BaseCoffeeBreakTestCase):
    def test_grupo_de_cada_momento_do_fluxo(self):
        casos = [
            ({"data_inicio_evento": HOJE + dt.timedelta(days=3)}, "entrega"),
            ({"data_inicio_evento": HOJE + dt.timedelta(days=30)}, ""),
            ({"data_inicio_evento": HOJE - dt.timedelta(days=2)}, "sem_nota"),
            ({"data_inicio_evento": HOJE - dt.timedelta(days=2), "numero_nota_fiscal": "10"}, "sem_oficio"),
            ({"numero_nota_fiscal": "10", "numero_oficio": "5/2026"}, "sem_protocolo"),
            ({"numero_nota_fiscal": "10", "protocolo_pagamento": "12.345.678-9"}, "sem_ob"),
            (
                {"numero_nota_fiscal": "10", "protocolo_pagamento": "12.345.678-9",
                 "data_atesto_gaf": HOJE, "data_ordem_bancaria": HOJE},
                "ob_nao_enviada",
            ),
            (
                {"numero_nota_fiscal": "10", "protocolo_pagamento": "12.345.678-9", "data_atesto_gaf": HOJE,
                 "data_ordem_bancaria": HOJE, "data_envio_empresa": HOJE},
                "",
            ),
            ({"data_inicio_evento": HOJE - dt.timedelta(days=2), "cancelada": True}, ""),
            ({}, ""),
        ]
        for campos, esperado in casos:
            with self.subTest(campos=campos):
                solicitacao = self.criar_solicitacao(**campos)
                self.assertEqual(services.proxima_acao(solicitacao, HOJE), esperado)

    def test_dias_parada_pelo_historico_e_pelo_fim_do_evento(self):
        solicitacao = self.criar_solicitacao(data_inicio_evento=HOJE - dt.timedelta(days=20))
        registro = services.registrar_historico(solicitacao, self.ascom, AcaoHistoricoCoffeeBreak.CRIACAO, "x")
        HistoricoCoffeeBreak.objects.filter(pk=registro.pk).update(
            criado_em=timezone.make_aware(dt.datetime(2026, 8, 1, 10))
        )
        # O evento (06/09) é depois do último registro (01/08): conta do evento.
        self.assertEqual(services.dias_parada(solicitacao, HOJE), 20)
        self.assertEqual(services.selo_parada(solicitacao, HOJE), "Parada há 20 dias")
        services.registrar_historico(solicitacao, self.ascom, AcaoHistoricoCoffeeBreak.ATUALIZACAO, "y")
        self.assertEqual(services.dias_parada(solicitacao, timezone.localdate()), 0)


class PainelFilaTests(BaseCoffeeBreakTestCase):
    def test_painel_agrupa_pela_proxima_acao_com_o_botao_que_resolve(self):
        entrega = self.criar_solicitacao(
            numero="11/2026", descricao_evento="Palestra na escola",
            data_inicio_evento=HOJE + dt.timedelta(days=2), local_entrega="Auditório central",
            responsavel_recebimento="Maria 41 90000-0000", horario_evento=dt.time(9, 30),
        )
        sem_nota = self.criar_solicitacao(
            numero="12/2026", descricao_evento="Formatura realizada", data_inicio_evento=HOJE - dt.timedelta(days=10),
        )
        _criada_em(sem_nota, dt.date(2026, 8, 1))
        self.client.force_login(self.ascom)
        with mock.patch("django.utils.timezone.localdate", return_value=HOJE):
            resposta = self.client.get(reverse("coffee_break:painel"))
        self.assertEqual(resposta.status_code, 200)
        grupos = {g["chave"]: g for g in resposta.context["fila"]}
        self.assertEqual([i["s"].pk for i in grupos["entrega"]["itens"]], [entrega.pk])
        self.assertEqual([i["s"].pk for i in grupos["sem_nota"]["itens"]], [sem_nota.pk])
        self.assertContains(resposta, "O que fazer hoje")
        self.assertContains(resposta, "Auditório central")
        self.assertContains(resposta, "Maria 41 90000-0000")
        self.assertContains(resposta, reverse("coffee_break:etapa_nota", args=[sem_nota.pk]))
        self.assertContains(resposta, "Anexar a nota")
        self.assertContains(resposta, "Parada há 10 dias")

    def test_lista_mostra_parada_ha_n_dias(self):
        _criada_em(self.criar_solicitacao(numero="13/2026", data_inicio_evento=HOJE - dt.timedelta(days=15)), dt.date(2026, 8, 1))
        self.client.force_login(self.ascom)
        with mock.patch("django.utils.timezone.localdate", return_value=HOJE):
            resposta = self.client.get(reverse("coffee_break:solicitacoes"))
        self.assertContains(resposta, "Parada há 15 dias")
