"""m096: o diário de bordo no celular do motorista, pelo link pessoal e sem login."""
from __future__ import annotations

import datetime
import json
from decimal import Decimal
from urllib.parse import unquote

from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Estado, Municipio, Regiao
from core.models import Notificacao
from viagens_roteiros.models import Roteiro, RoteiroTrecho

from .campo_services import gerar_link, validade_do_link
from .models import DiarioBordo, LancamentoDiarioCampo, LinkDiarioCampo
from .test_helpers import PrestacaoFixturesMixin
from .test_helpers import PrestacaoTestCase as TestCase


class DiarioCelularBase(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.setUpPrestacaoFixtures()
        estado, _ = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})
        regiao, _ = Regiao.objects.get_or_create(nome="Interior")
        self.sede = Municipio.objects.create(nome="Cidade Sede", estado=estado, regiao=regiao)
        self.destino = Municipio.objects.create(nome="Cidade Destino", estado=estado, regiao=regiao)
        self.motorista = self.criar_servidor("Motorista Sintético")
        self.motorista.telefone = "41999990000"
        self.motorista.save()
        self.colega = self.criar_servidor("Colega Sintético")
        self.fixture = self.criar_prestacao(numero=401, com_roteiro=False, servidores=[self.motorista, self.colega])
        self.oficio = self.fixture.oficio
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        agora = timezone.now()
        self.saida = agora + datetime.timedelta(days=1)
        self.retorno = agora + datetime.timedelta(days=3)
        roteiro = Roteiro.objects.create(saida_dt=self.saida, retorno_chegada_dt=self.retorno)
        RoteiroTrecho.objects.create(
            roteiro=roteiro, sentido=RoteiroTrecho.Sentido.IDA, ordem=0, saida_dt=self.saida,
            origem_municipio=self.sede, destino_municipio=self.destino, distancia_km=Decimal("100"),
        )
        RoteiroTrecho.objects.create(
            roteiro=roteiro, sentido=RoteiroTrecho.Sentido.RETORNO, ordem=1, chegada_dt=self.retorno,
            origem_municipio=self.destino, destino_municipio=self.sede,
        )
        self.oficio.roteiro = roteiro
        self.oficio.motorista = self.motorista
        self.oficio.save(update_fields=["roteiro", "motorista", "atualizado_em"])
        self.prestacao = type(self.prestacao).objects.get(pk=self.prestacao.pk)
        self.diario, _ = DiarioBordo.objects.get_or_create(prestacao=self.prestacao)
        self.link = gerar_link(self.diario, self.user)
        self.anonimo = Client()
        self.linhas = list(self.diario.trechos.order_by("ordem"))

    def enviar(self, lancamentos, *, token=None, **extra):
        cabecalhos = {"HTTP_X_DIARIO_CAMPO": "1", **extra}
        return self.anonimo.post(
            reverse("campo_diario:enviar", args=[token or self.link.token]),
            data=json.dumps({"lancamentos": lancamentos}),
            content_type="application/json",
            **cabecalhos,
        )

    def linha_pk(self, i=0):
        from .diario_services import sincronizar_trechos

        return [l.pk for l in sincronizar_trechos(DiarioBordo.objects.get(pk=self.diario.pk))][i]


class LinkDoDiarioTests(DiarioCelularBase):
    def test_pagina_abre_sem_login_e_mostra_so_o_necessario(self):
        resposta = self.anonimo.get(reverse("campo_diario:pagina", args=[self.link.token]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Ofício")
        self.assertContains(resposta, "CIDADE DESTINO")
        self.assertNotContains(resposta, "Colega Sintético")
        self.assertNotContains(resposta, self.motorista.cpf)
        self.assertEqual(resposta["Referrer-Policy"], "no-referrer")
        self.link.refresh_from_db()
        self.assertIsNotNone(self.link.ultimo_acesso_em)

    def test_token_invalido_revogado_e_vencido(self):
        self.assertEqual(self.anonimo.get(reverse("campo_diario:pagina", args=["x" * 43])).status_code, 404)
        self.assertEqual(self.enviar([], token="y" * 43).status_code, 404)
        LinkDiarioCampo.objects.filter(pk=self.link.pk).update(expira_em=timezone.now() - datetime.timedelta(minutes=1))
        self.assertEqual(self.anonimo.get(reverse("campo_diario:pagina", args=[self.link.token])).status_code, 410)
        self.assertEqual(self.enviar([{"id": "abcdefgh1", "linha": self.linha_pk(), "km_inicial": 1}]).status_code, 410)
        novo = gerar_link(self.diario, self.user)
        self.link.refresh_from_db()
        self.assertIsNotNone(self.link.revogado_em)  # gerar outro revoga o anterior
        self.assertEqual(self.anonimo.get(reverse("campo_diario:pagina", args=[novo.token])).status_code, 200)
        self.assertFalse(LancamentoDiarioCampo.objects.exists())

    def test_link_de_viagem_cancelada_nao_abre(self):
        type(self.oficio).objects.filter(pk=self.oficio.pk).update(cancelado=True)
        self.assertEqual(self.anonimo.get(reverse("campo_diario:pagina", args=[self.link.token])).status_code, 410)

    def test_validade_vai_alguns_dias_alem_do_retorno(self):
        self.assertGreater(self.link.expira_em, self.retorno)
        self.assertLessEqual(validade_do_link(self.prestacao), self.retorno + datetime.timedelta(days=5, seconds=1))

    def test_link_nao_abre_o_resto_do_sistema(self):
        resposta = self.anonimo.get(reverse("viagens_prestacoes:diario_servidor", args=[self.ps.pk]) + f"?token={self.link.token}")
        self.assertEqual(resposta.status_code, 302)

    def test_service_worker_e_manifesto(self):
        sw = self.anonimo.get(reverse("campo_diario:sw"))
        self.assertEqual(sw.status_code, 200)
        self.assertIn("javascript", sw["Content-Type"])
        manifesto = self.anonimo.get(reverse("campo_diario:manifest", args=[self.link.token]))
        self.assertEqual(json.loads(manifesto.content)["start_url"], reverse("campo_diario:pagina", args=[self.link.token]))


class SincronizacaoTests(DiarioCelularBase):
    def test_grava_no_diario_e_devolve_avisos_do_hodometro(self):
        resposta = self.enviar([
            {"id": "lanc-0001", "linha": self.linha_pk(0), "km_inicial": 1000, "km_final": 1300, "abastecimento": False},
        ])
        self.assertEqual(resposta.status_code, 200, resposta.content)
        dados = resposta.json()
        self.assertEqual(dados["resultados"][0]["situacao"], "gravado")
        linha = self.diario.trechos.get(pk=self.linha_pk(0))
        self.assertEqual((linha.km_inicial, linha.km_final, linha.abastecimento), (1000, 1300, False))
        # 300 km rodados contra 100 previstos: o aviso da prestação parte 2 volta junto.
        self.assertTrue(any("300 km rodados" in a for a in dados["estado"]["avisos"]))
        self.assertNotIn("oficio", json.dumps(dados["estado"]["ultimo_km"] or {}))
        self.ps.refresh_from_db()
        self.assertEqual(self.ps.status, self.ps.STATUS_EM_PREENCHIMENTO)

    def test_idempotente_pelo_id_do_celular(self):
        lanc = {"id": "lanc-0002", "linha": self.linha_pk(0), "km_inicial": 500}
        self.assertEqual(self.enviar([lanc]).json()["resultados"][0]["situacao"], "gravado")
        # Alguém corrige no escritório; o reenvio do mesmo lançamento não sobrescreve.
        self.diario.trechos.filter(pk=self.linha_pk(0)).update(km_inicial=700)
        segunda = self.enviar([lanc]).json()
        self.assertEqual(segunda["resultados"][0]["situacao"], "gravado")
        self.assertEqual(self.diario.trechos.get(pk=self.linha_pk(0)).km_inicial, 700)
        self.assertEqual(LancamentoDiarioCampo.objects.filter(cliente_id="lanc-0002").count(), 1)

    def test_km_invertido_e_recusado_sem_derrubar_os_outros(self):
        resposta = self.enviar([
            {"id": "lanc-0003", "linha": self.linha_pk(0), "km_inicial": 2000, "km_final": 1500},
            {"id": "lanc-0004", "linha": self.linha_pk(1), "km_inicial": 3000, "km_final": 3100},
        ]).json()
        self.assertEqual([r["situacao"] for r in resposta["resultados"]], ["recusado", "gravado"])
        self.assertIn("menor", resposta["resultados"][0]["mensagem"])
        self.assertIsNone(self.diario.trechos.get(pk=self.linha_pk(0)).km_inicial)
        self.assertEqual(self.diario.trechos.get(pk=self.linha_pk(1)).km_final, 3100)
        # O recusado também é idempotente: reenviado, a mesma resposta.
        again = self.enviar([{"id": "lanc-0003", "linha": self.linha_pk(0), "km_inicial": 1, "km_final": 2}]).json()
        self.assertEqual(again["resultados"][0]["situacao"], "recusado")

    def test_validacao_dos_campos(self):
        outro = self.criar_prestacao(numero=402, trechos_roteiro=1)
        diario_outro, _ = DiarioBordo.objects.get_or_create(prestacao=outro.prestacao)
        from .diario_services import sincronizar_trechos

        linha_de_outro = sincronizar_trechos(diario_outro)[0].pk
        casos = [
            {"id": "lanc-0010", "linha": linha_de_outro, "km_inicial": 10},  # linha de outro diário
            {"id": "lanc-0011", "linha": self.linha_pk(0), "km_inicial": -5},
            {"id": "lanc-0012", "linha": self.linha_pk(0), "km_inicial": "12a"},
            {"id": "lanc-0013", "linha": self.linha_pk(0), "km_final": 10**9},
            {"id": "lanc-0014", "linha": self.linha_pk(0), "abastecimento": "sim"},
            {"id": "lanc-0015", "linha": self.linha_pk(0), "km_inicial": True},
            {"id": "curto", "linha": self.linha_pk(0), "km_inicial": 1},
            {"id": "lanc-0016", "linha": self.linha_pk(0)},
        ]
        resultados = self.enviar(casos).json()["resultados"]
        self.assertTrue(all(r["situacao"] == "recusado" for r in resultados), resultados)
        self.assertIsNone(sincronizar_trechos(diario_outro)[0].km_inicial)
        self.assertIsNone(self.diario.trechos.get(pk=self.linha_pk(0)).km_inicial)

    def test_formato_tamanho_origem_e_taxa(self):
        url = reverse("campo_diario:enviar", args=[self.link.token])
        # Sem o cabeçalho próprio (um formulário de outro site não consegue mandá-lo).
        self.assertEqual(self.anonimo.post(url, data="{}", content_type="application/json").status_code, 400)
        self.assertEqual(self.anonimo.post(url, data={"lancamentos": "x"}, HTTP_X_DIARIO_CAMPO="1").status_code, 400)
        self.assertEqual(self.enviar([], HTTP_ORIGIN="https://outro-site.example").status_code, 403)
        grande = [{"id": f"lanc-{i:05d}", "linha": self.linha_pk(0), "km_inicial": i, "pad": "x" * 1000} for i in range(40)]
        self.assertEqual(self.enviar(grande).status_code, 413)
        muitos = [{"id": f"lanc-{i:05d}", "linha": self.linha_pk(0), "km_inicial": i} for i in range(51)]
        self.assertEqual(self.enviar(muitos).status_code, 400)
        cache.clear()
        from .campo_views import LIMITE_POR_LINK

        for _ in range(LIMITE_POR_LINK):
            self.enviar([])
        self.assertEqual(self.enviar([]).status_code, 429)

    def test_prestacao_finalizada_trava_o_link(self):
        self.prestacao.servidores_prestacao.update(finalizada=True)
        resposta = self.enviar([{"id": "lanc-0020", "linha": self.linha_pk(0), "km_inicial": 1}])
        self.assertEqual(resposta.status_code, 409)
        self.assertIsNone(self.diario.trechos.get(pk=self.linha_pk(0)).km_inicial)


class TelaDoOperadorTests(DiarioCelularBase):
    def test_gerar_revogar_e_whatsapp(self):
        url_diario = reverse("viagens_prestacoes:diario_servidor", args=[self.ps.pk])
        pagina = self.client.get(url_diario)
        self.assertContains(pagina, "Enviar por WhatsApp")
        whatsapp = pagina.context["link_campo_whatsapp"]
        self.assertTrue(whatsapp.startswith("https://wa.me/5541999990000?text="))
        texto = unquote(whatsapp.split("text=", 1)[1])
        self.assertIn(self.link.token, texto)
        self.assertIn("sem sinal", texto)
        self.client.post(reverse("viagens_prestacoes:diario_servidor_link_campo", args=[self.ps.pk, "revogar"]))
        self.assertIsNone(self.client.get(url_diario).context["link_campo"])
        self.client.post(reverse("viagens_prestacoes:diario_servidor_link_campo", args=[self.ps.pk, "gerar"]))
        self.assertEqual(LinkDiarioCampo.objects.filter(diario=self.diario, revogado_em__isnull=True).count(), 1)

    def test_gerar_exige_login(self):
        resposta = self.anonimo.post(reverse("viagens_prestacoes:diario_servidor_link_campo", args=[self.ps.pk, "gerar"]))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(LinkDiarioCampo.objects.filter(diario=self.diario).count(), 1)


class AvisosDaViagemTests(DiarioCelularBase):
    def test_amanha_sai_e_equipe_chegou_uma_vez_so(self):
        from .avisos import avisar_viagens

        self.assertEqual(avisar_viagens(), 1)
        self.assertEqual(avisar_viagens(), 0)
        aviso = Notificacao.objects.get(usuario=self.user)
        self.assertIn("Amanhã sai a viagem", aviso.titulo)
        self.assertIn("#celular", aviso.link)
        # Três dias depois, na volta: o aviso de chegada, também uma vez.
        depois = self.retorno + datetime.timedelta(hours=1)
        self.assertEqual(avisar_viagens(depois), 1)
        self.assertEqual(avisar_viagens(depois), 0)
        self.assertTrue(Notificacao.objects.filter(usuario=self.user, titulo__contains="chegou de viagem").exists())

    def test_chegada_antiga_nao_avisa(self):
        from .avisos import avisar_viagens

        self.assertEqual(avisar_viagens(self.retorno + datetime.timedelta(days=5)), 0)

    def test_comando(self):
        from io import StringIO

        from django.core.management import call_command

        saida = StringIO()
        call_command("avisar_prazos_prestacao", stdout=saida)
        self.assertIn("1 aviso", saida.getvalue())
