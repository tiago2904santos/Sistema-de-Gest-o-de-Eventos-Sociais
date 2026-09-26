"""Onda V-P2: hodômetro do diário (m078, m095, m088)."""
from __future__ import annotations

import json
from decimal import Decimal

from django.urls import reverse

from cadastros.models import Estado, Municipio, Regiao
from viagens_prestacoes.models import DiarioBordo
from viagens_roteiros.models import DistanciaMunicipios, Roteiro, RoteiroTrecho

from .test_helpers import PrestacaoFixturesMixin
from .test_helpers import PrestacaoTestCase as TestCase


class HodometroDoDiarioTests(PrestacaoFixturesMixin, TestCase):
    """m078/m095: distância prevista por trecho, sugestão e conferência (aviso, não bloqueio)."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        estado, _ = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})
        regiao, _ = Regiao.objects.get_or_create(nome="Interior")
        self.sede = Municipio.objects.create(nome="Cidade Sede", estado=estado, regiao=regiao)
        self.destino = Municipio.objects.create(nome="Cidade Destino", estado=estado, regiao=regiao)
        self.fixture = self.criar_prestacao(numero=301, com_roteiro=False)
        self.prestacao = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]
        roteiro = Roteiro.objects.create()
        RoteiroTrecho.objects.create(
            roteiro=roteiro, sentido=RoteiroTrecho.Sentido.IDA, ordem=0,
            origem_municipio=self.sede, destino_municipio=self.destino, distancia_km=Decimal("100.40"),
        )
        RoteiroTrecho.objects.create(
            roteiro=roteiro, sentido=RoteiroTrecho.Sentido.RETORNO, ordem=1,
            origem_municipio=self.destino, destino_municipio=self.sede,
        )
        self.fixture.oficio.roteiro = roteiro
        self.fixture.oficio.save(update_fields=["roteiro", "atualizado_em"])
        self.diario, _ = DiarioBordo.objects.get_or_create(prestacao=self.prestacao)

    def abrir(self):
        return self.client.get(reverse("viagens_prestacoes:diario_servidor", args=[self.ps.pk]))

    def autosave(self, **campos):
        return self.client.post(
            reverse("viagens_prestacoes:diario_servidor_autosave", args=[self.ps.pk]),
            data=json.dumps({"model": "diario_bordo", "object_id": str(self.diario.pk), "dirty_fields": list(campos), "fields": campos}),
            content_type="application/json",
        )

    def test_distancia_prevista_vem_do_trecho_e_serve_a_volta(self):
        resposta = self.abrir()
        self.assertEqual(resposta.status_code, 200)
        # A ida tem distância no roteiro; a volta, sem distância, usa o mesmo par guardado.
        self.assertEqual([i["prevista"] for i in resposta.context["hodometro"]["linhas"]], [100, 100])
        self.assertContains(resposta, 'data-prevista="100"', count=2)
        self.assertTrue(DistanciaMunicipios.objects.filter(origem=self.sede, destino=self.destino).exists())

    def test_autosave_devolve_totais_e_avisa_sem_bloquear(self):
        self.abrir()
        resposta = self.autosave(**{
            "form-0-km_inicial": "10.000", "form-0-km_final": "10.101",
            "form-1-km_inicial": "10.050", "form-1-km_final": "10.300",
        })
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertTrue(dados["ok"])
        hodometro = dados["hodometro"]
        self.assertEqual(hodometro["total_rodado"], 101 + 250)
        self.assertEqual(hodometro["total_previsto"], 200)
        avisos = " ".join(hodometro["avisos"])
        self.assertIn("voltou para trás", avisos)
        self.assertIn("250 km rodados", avisos)
        # Gravou mesmo com os avisos.
        linhas = list(self.diario.trechos.order_by("ordem"))
        self.assertEqual(linhas[1].km_final, 10300)

    def test_rodado_dentro_da_tolerancia_nao_avisa(self):
        self.abrir()
        dados = self.autosave(**{
            "form-0-km_inicial": "500", "form-0-km_final": "610",
            "form-1-km_inicial": "610", "form-1-km_final": "705",
        }).json()
        self.assertEqual(dados["hodometro"]["avisos"], [])

    def test_corrigir_distancia_pela_linha_vale_para_o_par(self):
        self.abrir()
        linha = self.diario.trechos.order_by("ordem").first()
        resposta = self.client.post(
            reverse("viagens_prestacoes:diario_servidor_distancia", args=[self.ps.pk, linha.pk]),
            {"distancia_km": "120,5"},
        )
        self.assertEqual(resposta.status_code, 302)
        registro = DistanciaMunicipios.objects.get(origem=self.sede, destino=self.destino)
        self.assertEqual(registro.distancia_km, Decimal("120.50"))
        self.assertEqual(registro.fonte, DistanciaMunicipios.Fonte.MANUAL)
        self.assertEqual([i["prevista"] for i in self.abrir().context["hodometro"]["linhas"]], [120, 120])


class UltimoKmDaViaturaTests(PrestacaoFixturesMixin, TestCase):
    """m088: só a informação do último km da viatura; nada vem preenchido."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        from viagens_cadastros.models import Viatura

        self.viatura = Viatura.objects.create(placa="TST1A23", modelo="SINTETICO")
        self.anterior = self.criar_prestacao(numero=401)
        self.atual = self.criar_prestacao(numero=402)
        for fixture in (self.anterior, self.atual):
            fixture.oficio.viatura = self.viatura
            fixture.oficio.save(update_fields=["viatura", "atualizado_em"])
        diario_anterior, _ = DiarioBordo.objects.get_or_create(prestacao=self.anterior.prestacao)
        self.client.get(reverse("viagens_prestacoes:diario_servidor", args=[self.anterior.prestacoes_servidor[0].pk]))
        diario_anterior.trechos.update(km_inicial=45000, km_final=45210)

    def test_mostra_o_ultimo_km_sem_preencher(self):
        resposta = self.client.get(reverse("viagens_prestacoes:diario_servidor", args=[self.atual.prestacoes_servidor[0].pk]))
        ultimo = resposta.context["hodometro"]["ultimo_km"]
        self.assertEqual(ultimo["km"], 45210)
        self.assertEqual(ultimo["oficio"], self.anterior.oficio.numero_formatado)
        self.assertContains(resposta, "Último km registrado desta viatura")
        diario = DiarioBordo.objects.get(prestacao=self.atual.prestacao)
        self.assertFalse(diario.trechos.filter(km_inicial__isnull=False).exists())

    def test_saida_abaixo_do_ultimo_km_avisa(self):
        from viagens_prestacoes.diario_services import conferir_hodometro

        self.client.get(reverse("viagens_prestacoes:diario_servidor", args=[self.atual.prestacoes_servidor[0].pk]))
        diario = DiarioBordo.objects.get(prestacao=self.atual.prestacao)
        diario.trechos.update(km_inicial=44000, km_final=44100)
        avisos = " ".join(conferir_hodometro(diario)["avisos"])
        self.assertIn("menor que o último km registrado desta viatura", avisos)

    def test_viatura_manual_nao_tem_historico(self):
        from viagens_prestacoes.diario_services import ultimo_km_da_viatura

        diario, _ = DiarioBordo.objects.get_or_create(prestacao=self.atual.prestacao)
        diario.viatura_modo = DiarioBordo.VIATURA_MODO_MANUAL
        diario.save()
        self.assertIsNone(ultimo_km_da_viatura(diario))


class DadosEprotocoloDaPrestacaoTests(PrestacaoFixturesMixin, TestCase):
    """m052: o painel "Dados para o eProtocolo" com Copiar na Etapa 3."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        from datetime import date

        self.fixture = self.criar_prestacao(numero=501)
        self.ps = self.fixture.prestacoes_servidor[0]
        self.ps.numero_solicitacao = "7654321"
        self.ps.prazo_limite_saque = date(2026, 9, 10)
        self.ps.save()

    def test_etapa_3_mostra_os_campos_com_copiar(self):
        resposta = self.client.get(reverse("viagens_prestacoes:documentos_servidor", args=[self.ps.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Dados para o eProtocolo")
        self.assertContains(resposta, 'data-copiar="7654321"')
        self.assertContains(resposta, "js/components/copiar.js")
        campos = {c["rotulo"]: c["valor"] for c in resposta.context["eprotocolo"]["campos"]}
        self.assertEqual(campos["Nº/Ano do ofício"], self.fixture.oficio.numero_formatado)
        self.assertEqual(campos["Prazo limite de saque"], "10/09/2026")
        self.assertTrue(campos["Prestar contas até"])
        detalhamento = resposta.context["eprotocolo"]["textos"][0]["texto"]
        self.assertIn("SOLICITAÇÃO Nº 7654321", detalhamento)
        self.assertIn(self.ps.servidor.nome.upper(), detalhamento)


class PacotesDaEquipeZipTests(PrestacaoFixturesMixin, TestCase):
    """m098: os pacotes finais da equipe num ZIP, com PENDENCIAS.txt."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        self.ana = self.criar_servidor("Ana Sintetica")
        self.bruno = self.criar_servidor("Bruno Sintetico")
        self.fixture = self.criar_prestacao(numero=601, servidores=[self.ana, self.bruno])
        self.ps_ana, self.ps_bruno = self.fixture.prestacoes_servidor

    def test_zip_com_um_pdf_por_servidor_pronto_e_pendencias(self):
        import io
        from unittest import mock
        from zipfile import ZipFile

        from viagens_prestacoes import services

        def pendencias(ps):
            return [] if ps.pk == self.ps_ana.pk else ["Anexe o comprovante de saque/transferência deste servidor, acima."]

        with mock.patch.object(services, "pendencias_consolidado", side_effect=pendencias), \
                mock.patch.object(services, "gerar_prestacao_consolidado_pdf", return_value=b"%PDF-1.4 sintetico"):
            resposta = self.client.get(reverse("viagens_prestacoes:prestacao_pacotes_zip", args=[self.fixture.prestacao.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/zip")
        with ZipFile(io.BytesIO(resposta.content)) as arquivo:
            nomes = arquivo.namelist()
            self.assertIn("PENDENCIAS.txt", nomes)
            pdfs = [n for n in nomes if n.endswith(".pdf")]
            self.assertEqual(len(pdfs), 1)
            self.assertIn("Ana", pdfs[0])
            texto = arquivo.read("PENDENCIAS.txt").decode()
        self.assertIn("BRUNO SINTETICO", texto.upper())
        self.assertIn("comprovante", texto)

    def test_menu_do_oficio_tem_o_zip(self):
        resposta = self.get_listagem()
        self.assertContains(resposta, reverse("viagens_prestacoes:prestacao_pacotes_zip", args=[self.fixture.prestacao.pk]))

    def test_arquivo_avulso_leva_o_primeiro_nome(self):
        from viagens_prestacoes.download_views import _sufixo_servidor

        self.assertEqual(_sufixo_servidor(self.ps_ana), "_Ana")


class RelatorioTecnicoPreenchidoTests(PrestacaoFixturesMixin, TestCase):
    """m097: o RT começa com o ofício, a viagem e o plano; copia de outra prestação; salva modelo."""

    def setUp(self):
        super().setUp()
        self.setUpPrestacaoFixtures()
        from viagens_planos.models import PlanoTrabalho
        from viagens_viagem.models import Viagem

        self.viagem = Viagem.objects.create(titulo="Evento sintético", descricao="Atender a comunidade no evento sintético.")
        PlanoTrabalho.objects.create(
            viagem=self.viagem, contextualizacao="Contexto sintético.", metas="Meta sintética.",
            atividades="Atividade sintética.", consideracao_final="Considerações sintéticas.",
        )
        self.fixture = self.criar_prestacao(numero=701)
        self.fixture.oficio.viagem = self.viagem
        self.fixture.oficio.motivo = ""
        self.fixture.oficio.save()
        self.ps = self.fixture.prestacoes_servidor[0]

    def test_campos_vazios_vem_do_plano_e_da_viagem(self):
        resposta = self.client.get(reverse("viagens_prestacoes:rt_servidor", args=[self.ps.pk]))
        self.assertEqual(resposta.status_code, 200)
        form = resposta.context["form"]
        self.assertEqual(form["motivo"].value(), "Contexto sintético.")
        self.assertEqual(form["atividade"].value(), "Atender a comunidade no evento sintético.")
        self.assertEqual(form["conclusao"].value(), "Considerações sintéticas.")

    def test_texto_ja_escrito_nao_e_trocado(self):
        from viagens_prestacoes.rt_services import obter_ou_criar_relatorio_tecnico

        relatorio = obter_ou_criar_relatorio_tecnico(self.fixture.prestacao)
        relatorio.conclusao = "Conclusão do operador."
        relatorio.save()
        resposta = self.client.get(reverse("viagens_prestacoes:rt_servidor", args=[self.ps.pk]))
        self.assertEqual(resposta.context["form"]["conclusao"].value(), "Conclusão do operador.")

    def test_copiar_de_outra_prestacao_do_mesmo_evento(self):
        from viagens_prestacoes.models import RelatorioTecnico

        outra = self.criar_prestacao(numero=702)
        outra.oficio.viagem = self.viagem
        outra.oficio.save()
        RelatorioTecnico.objects.create(prestacao=outra.prestacao, conclusao="Conclusão anterior.")
        resposta = self.client.get(reverse("viagens_prestacoes:rt_servidor", args=[self.ps.pk]))
        opcoes = resposta.context["rts_copiar"]
        self.assertEqual(len(opcoes), 1)
        self.assertIn("mesmo evento", opcoes[0]["rotulo"])
        self.assertEqual(opcoes[0]["textos"]["conclusao"], "Conclusão anterior.")
        self.assertContains(resposta, 'id="rt-copiar"')

    def test_salvar_como_modelo(self):
        from viagens_prestacoes.models import ModeloTextoRelatorioTecnico

        url = reverse("viagens_prestacoes:modelo_criar_do_campo")
        dados = {"campo": "conclusao", "nome": "Padrão sintético", "texto": "Texto do modelo."}
        primeira = self.client.post(url, dados).json()
        segunda = self.client.post(url, dados).json()
        self.assertTrue(primeira["ok"])
        self.assertEqual(segunda["nome"], "Padrão sintético (2)")
        self.assertEqual(ModeloTextoRelatorioTecnico.objects.filter(campo="conclusao").count(), 2)
        self.assertEqual(self.client.post(url, {"campo": "conclusao", "texto": ""}).status_code, 400)
