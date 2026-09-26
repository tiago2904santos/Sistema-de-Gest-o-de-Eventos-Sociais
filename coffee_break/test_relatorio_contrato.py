"""Relatório do contrato para aditivo, reforço de empenho ou nova licitação (m037)."""

import datetime as dt
from decimal import Decimal
from unittest import mock, skipUnless

from django.urls import reverse

from documentos.services.pdf_renderer import weasyprint_disponivel

from . import relatorio_contrato, services
from .models import LoteCoffeeBreak, OcorrenciaEntrega, TipoOcorrencia
from .tests import BaseCoffeeBreakTestCase

HOJE = dt.date(2026, 9, 26)


class RelatorioDoContratoTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.contrato.vigencia_fim = dt.date(2026, 12, 31)
        self.contrato.valor_unitario = Decimal("20.00")
        self.contrato.save()
        self.lote.valor_empenho = Decimal("2000.00")
        self.lote.save()
        # Junho, julho e agosto: 20 por mês; setembro ainda não conta no ritmo.
        for i, (mes, quantidade) in enumerate([(6, 20), (7, 20), (8, 20), (9, 10)]):
            self.criar_solicitacao(
                numero=f"{60 + i}/2026", quantidade=quantidade, municipio=self.curitiba,
                data_inicio_evento=dt.date(2026, mes, 10), valor_unitario=Decimal("20.00"),
                data_emissao_nf=dt.date(2026, mes, 11) if mes == 6 else None,
                numero_nota_fiscal="1" if mes == 6 else "", protocolo_pagamento="12.345.678-9" if mes == 6 else "",
                data_atesto_gaf=dt.date(2026, 6, 12) if mes == 6 else None,
                data_ordem_bancaria=dt.date(2026, 7, 1) if mes == 6 else None,
            )

    def test_montar_consumo_projecao_e_valores(self):
        dados = relatorio_contrato.montar(self.contrato, HOJE)
        self.assertEqual([m["quantidade"] for m in dados["por_mes"]], [20, 20, 20, 10])
        self.assertEqual(dados["por_municipio"][0]["municipio"], "Curitiba")
        self.assertEqual(dados["restante"], 30)
        self.assertEqual(dados["projecao"]["ritmo"], 20.0)
        # 30 de saldo a 20 por mês: acaba em ~1,5 mês, antes de 31/12.
        self.assertTrue(dados["projecao"]["acaba_antes"])
        self.assertGreater(dados["projecao"]["falta"], 0)
        self.assertEqual(dados["gasto"], Decimal("1400.00"))
        self.assertEqual(dados["pago"], Decimal("400.00"))
        self.assertEqual(dados["saldo_empenho"], Decimal("600.00"))
        self.assertEqual(dados["prazo_medio_pagamento"], 20)

    def test_alerta_do_painel_passa_a_ser_a_projecao(self):
        lotes = list(LoteCoffeeBreak.objects.com_consumo().select_related("contrato"))
        em_alerta = services.lotes_em_alerta(lotes, HOJE)
        self.assertEqual([lote.pk for lote in em_alerta], [self.lote.pk])
        self.assertIn("antes do fim do contrato", em_alerta[0].motivo_alerta)
        # Vigência curta: o saldo dura até o fim do contrato, sem alerta.
        self.contrato.vigencia_fim = dt.date(2026, 10, 15)
        self.contrato.save()
        lotes = list(LoteCoffeeBreak.objects.com_consumo().select_related("contrato"))
        self.assertEqual(services.lotes_em_alerta(lotes, HOJE), [])

    def test_tela_csv_e_pdf(self):
        self.client.force_login(self.ascom)
        OcorrenciaEntrega.objects.create(
            solicitacao=self.lote.solicitacoes.first(), tipo=TipoOcorrencia.FALTA, avaliacao=3, descricao="Faltou suco"
        )
        url = reverse("coffee_break:relatorio_contrato", args=[self.contrato.pk])
        with mock.patch("django.utils.timezone.localdate", return_value=HOJE):
            tela = self.client.get(url)
            self.assertContains(tela, "O saldo acaba antes do fim do contrato")
            self.assertContains(tela, "Falta de itens (1)")
            csv = self.client.get(url + "?formato=csv")
        self.assertEqual(csv["Content-Type"], "text/csv; charset=utf-8")
        conteudo = csv.content.decode("utf-8")
        self.assertIn("jun/2026;1;20;400,00", conteudo)
        self.assertIn("Curitiba;4;70", conteudo)
        with mock.patch("coffee_break.documentos._pdf", return_value=b"%PDF-relatorio") as gerar:
            pdf = self.client.get(url + "?formato=pdf")
        self.assertEqual(pdf.content, b"%PDF-relatorio")
        self.assertEqual(gerar.call_args[0][0], "coffee_break/documentos/relatorio_contrato.html")

    @skipUnless(weasyprint_disponivel(), "WeasyPrint sem as bibliotecas nativas")
    def test_pdf_de_verdade(self):
        self.client.force_login(self.ascom)
        resposta = self.client.get(reverse("coffee_break:relatorio_contrato", args=[self.contrato.pk]) + "?formato=pdf")
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertTrue(resposta.content.startswith(b"%PDF"))
