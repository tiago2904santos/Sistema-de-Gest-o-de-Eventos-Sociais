"""Horário real e todos os destinos na Agenda (m132)."""

from datetime import date, datetime, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Estado, Municipio, Regiao
from demandas_eventos.models import DemandaEvento
from viagens_roteiros.models import Roteiro, RoteiroDestino
from viagens_viagem.models import Viagem

User = get_user_model()


def quando(dia, hora, minuto=0):
    return timezone.make_aware(datetime(2026, 10, dia, hora, minuto))


class HorariosEDestinos(TestCase):
    @classmethod
    def setUpTestData(cls):
        pr = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        regiao = Regiao.objects.create(nome="Região Horário")
        cls.sede = Municipio.objects.create(nome="Curitiba Hora", estado=pr, regiao=regiao)
        cls.maringa = Municipio.objects.create(nome="Maringá Hora", estado=pr, regiao=regiao)
        cls.londrina = Municipio.objects.create(nome="Londrina Hora", estado=pr, regiao=regiao)
        cls.root = User.objects.create_superuser("root_horarios", "root_horarios@example.com", None)

    def setUp(self):
        self.client.force_login(self.root)

    def eventos(self):
        return {e["id"]: e for e in self.client.get(reverse("agenda:eventos"), {"start": "2026-10-01", "end": "2026-11-01"}).json()}

    def viagem(self, inicio, fim, **campos):
        dados = {"titulo": "Teste", "destino_municipio": self.maringa, "destino_estado": self.maringa.estado, "data_inicio": inicio, "data_fim": fim}
        dados.update(campos)
        return Viagem.objects.create(**dados)

    def test_viagem_de_um_dia_com_roteiro_entra_com_hora(self):
        v = self.viagem(date(2026, 10, 12), date(2026, 10, 12))
        r = Roteiro.objects.create(viagem=v, origem_municipio=self.sede, saida_dt=quando(12, 6), retorno_chegada_dt=quando(12, 22))
        RoteiroDestino.objects.create(roteiro=r, municipio=self.londrina)
        ev = self.eventos()[f"viagem-{v.pk}"]
        self.assertFalse(ev["allDay"])
        self.assertEqual(ev["start"], "2026-10-12T06:00")
        self.assertEqual(ev["end"], "2026-10-12T22:00")
        self.assertEqual(ev["extendedProps"]["horario"], "06:00–22:00")
        # O município do trecho entra no filtro, e o título fica com o destino da viagem.
        self.assertIn("Londrina Hora/PR", ev["extendedProps"]["municipios"])
        self.assertEqual(ev["extendedProps"]["municipio"], "Maringá Hora/PR")

    def test_viagem_de_varios_dias_continua_dia_inteiro_com_o_horario_no_titulo(self):
        v = self.viagem(date(2026, 10, 12), date(2026, 10, 14), horario_inicio=time(6, 0), horario_fim=time(22, 0))
        ev = self.eventos()[f"viagem-{v.pk}"]
        self.assertTrue(ev["allDay"])
        self.assertEqual(ev["start"], "2026-10-12")
        self.assertEqual(ev["end"], "2026-10-15")
        self.assertIn("06:00–22:00", ev["title"])

    def test_todos_os_destinos_da_viagem_no_titulo_e_no_filtro(self):
        v = self.viagem(date(2026, 10, 12), date(2026, 10, 13),
                        destinos_extras=[{"estado": self.londrina.estado_id, "municipio": self.londrina.pk}])
        ev = self.eventos()[f"viagem-{v.pk}"]
        self.assertTrue(ev["title"].startswith("Maringá Hora/PR, Londrina Hora/PR"))
        self.assertEqual(ev["extendedProps"]["municipios"], ["Maringá Hora/PR", "Londrina Hora/PR"])
        dossie = self.client.get(reverse("agenda:detalhe", args=["viagem", v.pk])).content.decode()
        self.assertIn("Maringá Hora/PR, Londrina Hora/PR", dossie)

    def test_palestra_com_hora_de_inicio_dura_duas_horas(self):
        d = DemandaEvento.objects.create(data_solicitacao=date(2026, 9, 1), solicitante="Escola",
                                         data_inicio_evento=date(2026, 10, 12), hora_inicio=time(14, 30))
        ev = self.eventos()[f"demanda-{d.pk}"]
        self.assertFalse(ev["allDay"])
        self.assertEqual(ev["start"], "2026-10-12T14:30")
        self.assertEqual(ev["end"], "2026-10-12T16:30")

    def test_sem_horario_segue_dia_inteiro(self):
        v = self.viagem(date(2026, 10, 12), date(2026, 10, 12))
        ev = self.eventos()[f"viagem-{v.pk}"]
        self.assertTrue(ev["allDay"])
        self.assertEqual(ev["end"], "2026-10-13")
