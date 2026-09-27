"""Feriados e pontos facultativos na Agenda (m138): faixa de fundo, municipais só com compromisso na cidade."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Estado, Municipio, Regiao
from core import feriados
from core.models import Feriado
from viagens_viagem.models import Viagem

from . import fontes

User = get_user_model()


class FeriadosNaAgenda(TestCase):
    @classmethod
    def setUpTestData(cls):
        pr = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        regiao = Regiao.objects.create(nome="Região Feriado")
        cls.maringa = Municipio.objects.create(nome="Maringá Fer", estado=pr, regiao=regiao)
        cls.londrina = Municipio.objects.create(nome="Londrina Fer", estado=pr, regiao=regiao)
        cls.root = User.objects.create_superuser("root_feriados", "root_feriados@example.com", None)
        cls.comum = User.objects.create_user("comum_feriados", password="x")
        Feriado.objects.create(data=date(2026, 5, 10), nome="Aniversário de Maringá", anual=True, municipio=cls.maringa)
        Feriado.objects.create(data=date(2026, 12, 19), nome="Emancipação do Paraná", anual=True)

    def setUp(self):
        feriados.limpar_cache()
        self.addCleanup(feriados.limpar_cache)

    def eventos(self, usuario, inicio, fim):
        self.client.force_login(usuario)
        return self.client.get(reverse("agenda:eventos"), {"start": inicio, "end": fim, "fontes": "feriado"}).json()

    def test_feriado_nacional_e_geral_viram_faixa_de_fundo_para_todo_mundo(self):
        lista = self.eventos(self.comum, "2026-12-01", "2027-01-01")
        self.assertIn("feriado", {f.slug for f in fontes.fontes_de(self.comum)})
        por_nome = {e["title"]: e for e in lista}
        self.assertIn("Natal", por_nome)
        self.assertIn("Emancipação do Paraná", por_nome)
        natal = por_nome["Natal"]
        self.assertEqual(natal["display"], "background")
        self.assertEqual((natal["start"], natal["end"]), ("2026-12-25", "2026-12-26"))
        self.assertIn("ag-feriado", natal["classNames"])
        self.assertTrue(natal["extendedProps"]["fundo"])

    def test_municipal_so_quando_ha_compromisso_na_cidade(self):
        sem = {e["title"] for e in self.eventos(self.root, "2026-05-01", "2026-06-01")}
        self.assertNotIn("Aniversário de Maringá (Maringá Fer)", sem)

        Viagem.objects.create(titulo="Ida a Maringá", destino_municipio=self.maringa, destino_estado=self.maringa.estado,
                              data_inicio=date(2026, 5, 20), data_fim=date(2026, 5, 21))
        com = {e["title"]: e for e in self.eventos(self.root, "2026-05-01", "2026-06-01")}
        self.assertIn("Aniversário de Maringá (Maringá Fer)", com)
        self.assertIn("ag-feriado--municipal", com["Aniversário de Maringá (Maringá Fer)"]["classNames"])
        # Quem não vê Viagens não fica sabendo do destino — nem do feriado dele.
        self.assertNotIn("Aniversário de Maringá (Maringá Fer)", {e["title"] for e in self.eventos(self.comum, "2026-05-01", "2026-06-01")})

    def test_a_fonte_pode_ser_desligada(self):
        self.client.force_login(self.root)
        lista = self.client.get(reverse("agenda:eventos"), {"start": "2026-12-01", "end": "2027-01-01", "fontes": "viagem"}).json()
        self.assertEqual([e for e in lista if e["extendedProps"]["fonte"] == "feriado"], [])
