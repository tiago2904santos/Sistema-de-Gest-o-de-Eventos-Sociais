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
    "routes", "pages", "components", "forms", "tables", "modals", "dialogs", "navigation", "permissions",
    "integrations", "entities", "documents", "tokens", "assets", "styles", "states", "duplication-report",
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
        esquema = json.loads((Path(__file__).resolve().parents[1] / "docs/agent/audit-finding.schema.json").read_text(encoding="utf-8"))
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
        finally:
            timezone.now = original
