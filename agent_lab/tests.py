"""Testes do próprio laboratório: se a ferramenta mente, o agente mente junto."""

import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from agent_lab import audit_static, depgraph, inventory
from agent_lab.seed import ANCORA, CENARIOS, Semeador
from agent_lab.specimens import ESTADOS, all_specimens

ARQUIVOS_INVENTARIO = [
    "routes",
    "pages",
    "components",
    "forms",
    "tables",
    "modals",
    "dialogs",
    "navigation",
    "permissions",
    "integrations",
    "entities",
    "documents",
    "tokens",
    "assets",
    "styles",
    "states",
    "duplication-report",
]


class InventarioTests(TestCase):
    def test_gera_todos_os_arquivos_e_sem_erro_de_coletor(self):
        with tempfile.TemporaryDirectory() as d:
            resumo = inventory.gerar(Path(d))
            for nome in ARQUIVOS_INVENTARIO:
                dados = json.loads((Path(d) / f"{nome}.json").read_text(encoding="utf-8"))
                self.assertNotIn("error", dados, f"coletor {nome} falhou: {dados.get('error')}")
            self.assertGreater(resumo["routes"], 100)
            self.assertGreater(resumo["entities"], 50)

    def test_rotas_trazem_view_arquivo_e_modulo(self):
        rotas = inventory.coletar_rotas()["routes"]
        oficios = next(r for r in rotas if r["name"] == "viagens_oficios:lista")
        self.assertEqual(oficios["module_code"], "VIAGENS")
        self.assertTrue(oficios["file"].startswith("viagens_oficios/"))

    def test_saida_deterministica(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            inventory.gerar(Path(a), com_contagem=False)
            inventory.gerar(Path(b), com_contagem=False)
            for nome in ("routes", "entities", "tokens", "components"):
                self.assertEqual((Path(a) / f"{nome}.json").read_text(), (Path(b) / f"{nome}.json").read_text(), nome)


class SeedTests(TestCase):
    def test_small_cria_papeis_e_dados_sem_erro(self):
        relatorio, erros = Semeador("small").executar()
        self.assertEqual(erros, {})
        User = get_user_model()
        self.assertTrue(User.objects.filter(username="lab.admin", is_superuser=True).exists())
        self.assertTrue(User.objects.get(username="lab.troca_senha").deve_trocar_senha)
        self.assertEqual(relatorio["solicitacoes_evento"], CENARIOS["small"])

    def test_edge_case_sem_erro(self):
        _, erros = Semeador("edge_case").executar()
        self.assertEqual(erros, {})

    def test_deterministico(self):
        from viagens_cadastros.models import Servidor

        Semeador("small").executar()
        primeiro = list(Servidor.objects.order_by("pk").values_list("nome", "cpf"))
        Servidor.objects.all().delete()
        Semeador("small").executar()
        self.assertEqual(primeiro, list(Servidor.objects.order_by("pk").values_list("nome", "cpf")))

    def test_base_idempotente(self):
        Semeador("empty").executar()
        Semeador("empty").executar()
        self.assertEqual(get_user_model().objects.filter(username__startswith="lab.").count(), 10)

    def test_datas_ancoradas(self):
        from solicitacoes.models import SolicitacaoEvento

        Semeador("small").executar()
        datas = SolicitacaoEvento.objects.values_list("data_inicio_evento", flat=True)
        self.assertTrue(all(abs((d - ANCORA).days) <= 60 for d in datas))

    @override_settings(DEBUG=False)
    def test_comandos_recusam_sem_debug(self):
        with self.assertRaises(CommandError):
            call_command("agent_seed", scenario="empty")


class LabViewsTests(TestCase):
    @override_settings(DEBUG=True)
    def test_todos_os_especimes_renderizam(self):
        for spec in all_specimens():
            self.assertIn(spec.state, ESTADOS, spec.id)
            resp = self.client.get(f"/_lab/c/{spec.id}/")
            self.assertEqual(resp.status_code, 200, spec.id)
            self.assertNotContains(resp, "data-error", msg_prefix=spec.id)

    @override_settings(DEBUG=True)
    def test_indice_e_health(self):
        self.assertEqual(self.client.get("/_lab/").status_code, 200)
        resp = self.client.get("/_lab/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["db_ok"])

    @override_settings(DEBUG=False)
    def test_fora_do_debug_so_superusuario(self):
        self.assertEqual(self.client.get("/_lab/").status_code, 404)
        admin = get_user_model().objects.create_superuser("root-lab", "r@lab.invalid", "x")
        self.client.force_login(admin)
        self.assertEqual(self.client.get("/_lab/specimens.json").status_code, 200)

    @override_settings(DEBUG=True)
    def test_previa_das_paginas_de_erro(self):
        self.assertEqual(self.client.get("/_lab/erro/404/").status_code, 404)
        self.assertEqual(self.client.get("/_lab/erro/500/").status_code, 500)


class AuditoriaTests(TestCase):
    def test_achados_seguem_o_esquema(self):
        esquema = json.loads(
            (Path(__file__).resolve().parents[1] / "docs/agent/audit-finding.schema.json").read_text(encoding="utf-8")
        )
        obrigatorios = set(esquema["required"])
        with tempfile.TemporaryDirectory() as d:
            resumo = audit_static.executar(Path(d))
            dados = json.loads((Path(d) / "static-findings.json").read_text(encoding="utf-8"))
        self.assertEqual(resumo["total"], len(dados["findings"]))
        for a in dados["findings"]:
            self.assertTrue(obrigatorios <= set(a), a["id"])
            self.assertIn(a["severity"], esquema["properties"]["severity"]["enum"])
            self.assertIn(a["category"], esquema["properties"]["category"]["enum"])

    def test_depgraph(self):
        with tempfile.TemporaryDirectory() as d:
            r = depgraph.gerar(Path(d))
            self.assertGreater(r["app_import_edges"], 10)
            self.assertTrue((Path(d) / "app-imports.mmd").read_text().startswith("%%"))

    def test_ciclos_tarjan(self):
        self.assertEqual(depgraph.ciclos({("a", "b"): 1, ("b", "a"): 1, ("b", "c"): 1}), [["a", "b"]])


class RelogioAncoradoTests(TestCase):
    def test_ancorar_move_now_para_a_data(self):
        from django.utils import timezone

        from agent_lab import clock

        original = timezone.now
        try:
            clock.ancorar("2026-09-15T10:00:00-03:00")
            self.assertEqual(timezone.localdate().isoformat(), "2026-09-15")
            self.assertIs(timezone.now, original, "precisa ser o mesmo objeto (migrações comparam identidade)")
        finally:
            clock.desancorar()
        self.assertNotEqual(timezone.localdate().isoformat(), "2026-09-15")


class AmbienteTests(TestCase):
    def test_banco_de_teste_sem_marca_e_dev(self):
        from agent_lab.environment import detectar

        with override_settings(DEBUG=True):
            self.assertEqual(detectar()["environment"], "DEV")

    def test_marca_interna_torna_lab_e_libera_reset(self):
        from agent_lab.environment import exigir, gravar_marca

        gravar_marca()
        with override_settings(DEBUG=True):
            self.assertEqual(exigir("reset")["environment"], "LAB")

    def test_sem_debug_e_production_somente_leitura(self):
        from agent_lab.environment import AmbienteRecusado, detectar, exigir, gravar_marca

        gravar_marca()  # nem a marca libera escrita sem DEBUG
        with override_settings(DEBUG=False):
            self.assertEqual(detectar()["environment"], "PRODUCTION")
            with self.assertRaises(AmbienteRecusado):
                exigir("write")

    def test_declaracao_so_aumenta_risco(self):
        import os

        from agent_lab.environment import detectar, gravar_marca

        gravar_marca()
        os.environ["APP_ENVIRONMENT"] = "production"
        try:
            with override_settings(DEBUG=True):
                self.assertEqual(detectar()["environment"], "PRODUCTION")
        finally:
            del os.environ["APP_ENVIRONMENT"]


class InteligenciaTests(TestCase):
    def test_explain_recusa_escrita_e_multiplas_instrucoes(self):
        from agent_lab.db_intel import ConsultaRecusada, validar_select

        for ruim in (
            "DELETE FROM x",
            "select 1; drop table x",
            "WITH a AS (DELETE FROM x RETURNING *) SELECT * FROM a",
            "update x set y=1",
        ):
            with self.assertRaises(ConsultaRecusada, msg=ruim):
                validar_select(ruim)
        self.assertEqual(validar_select("select 'drop' as texto;"), "select 'drop' as texto")

    def test_contrato_detecta_campo_removido_e_tipo_alterado(self):
        from agent_lab.api_intel import comparar, inferir

        antes = {"/x/": {"schema": inferir({"results": [{"id": 1, "nome": "a"}], "total": 1})}}
        depois = {"/x/": {"schema": inferir({"results": [{"id": "1"}], "total": 1})}}
        quebras, _ = comparar(depois, antes)
        problemas = {q["problem"] for q in quebras}
        self.assertIn("campo removido: results.[].nome", problemas)
        self.assertIn("tipo mudou em results.[].id: integer → string", problemas)

    def test_consultas_devolvem_fonte(self):
        from agent_lab import query

        r = query.route("/viagens/oficios/")
        self.assertEqual(r["name"], "viagens_oficios:lista")
        self.assertTrue(any("views.py" in s for s in r["sources"]))
        self.assertEqual(query.model("viagens_oficios.Oficio")["model"], "viagens_oficios.Oficio")
        self.assertGreaterEqual(query.known_problems("P1")["count"], 1)

    def test_seed_sempre_ancorado(self):
        from solicitacoes.models import SolicitacaoEvento

        Semeador("small").executar()
        criados = {d.date() for d in SolicitacaoEvento.objects.values_list("criado_em", flat=True)}
        self.assertEqual(criados, {ANCORA})

    def test_cenario_sob_medida(self):
        import tempfile as tf

        from agent_lab import seed

        with tf.TemporaryDirectory() as d, override_settings(BASE_DIR=Path(d)):
            dados = seed.criar_cenario("so-viagens", volume=2, modules=["viagens_cadastros"])
            self.assertEqual(seed.carregar_cenario("so-viagens")["modules"], ["viagens_cadastros"])
            rel, erros = Semeador("so-viagens", custom=dados).executar()
            self.assertEqual(erros, {})
            self.assertNotIn("solicitacoes_evento", rel)
