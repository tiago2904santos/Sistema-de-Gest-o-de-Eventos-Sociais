"""Choques de agenda no calendário (m130): ag-conflito nos eventos e a seção do dossiê."""

from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Estado, Municipio, Regiao
from demandas_eventos.models import DemandaEvento, Palestrante
from viagens_cadastros.models import Servidor, Viatura
from viagens_oficios.models import Oficio
from viagens_roteiros.models import Roteiro, RoteiroDestino
from viagens_viagem.models import Viagem

from . import conflitos

User = get_user_model()


def quando(dia, hora):
    return timezone.make_aware(datetime(2026, 10, dia, hora))


class ConflitosNaAgenda(TestCase):
    @classmethod
    def setUpTestData(cls):
        pr = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        regiao = Regiao.objects.create(nome="Região Agenda")
        cls.sede = Municipio.objects.create(nome="Curitiba Agenda", estado=pr, regiao=regiao)
        cls.destino = Municipio.objects.create(nome="Maringá Agenda", estado=pr, regiao=regiao)
        cls.ana = Servidor.objects.create(nome="ANA AGENDA")
        cls.viatura = Viatura.objects.create(placa="BBB2C34", modelo="VIATURA AGENDA")
        cls.root = User.objects.create_superuser("root_agenda_conf", "root_agenda_conf@example.com", None)

    def viagem_com_oficio(self, saida, chegada, *, servidores=(), viatura=None, numero=None):
        viagem = Viagem.objects.create(
            titulo="Viagem", destino_municipio=self.destino, destino_estado=self.destino.estado,
            data_inicio=saida.date(), data_fim=chegada.date(),
        )
        roteiro = Roteiro.objects.create(origem_municipio=self.sede, saida_dt=saida, retorno_chegada_dt=chegada, viagem=viagem)
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.destino)
        oficio = Oficio.objects.create(viagem=viagem, roteiro=roteiro, viatura=viatura, numero=numero, ano=2026 if numero else None)
        oficio.servidores.set(servidores)
        return viagem, oficio

    def eventos(self):
        self.client.force_login(self.root)
        return self.client.get(reverse("agenda:eventos"), {"start": "2026-10-01", "end": "2026-11-01"}).json()

    def test_viagens_com_a_mesma_pessoa_ao_mesmo_tempo_ganham_ag_conflito(self):
        a, _ = self.viagem_com_oficio(quando(12, 8), quando(12, 18), servidores=[self.ana], numero=12)
        b, _ = self.viagem_com_oficio(quando(12, 14), quando(13, 10), servidores=[self.ana], viatura=self.viatura)
        c, _ = self.viagem_com_oficio(quando(20, 8), quando(20, 18), servidores=[self.ana])
        por_id = {e["id"]: e for e in self.eventos()}
        self.assertIn("ag-conflito", por_id[f"viagem-{a.pk}"]["classNames"])
        self.assertIn("ag-conflito", por_id[f"viagem-{b.pk}"]["classNames"])
        self.assertNotIn("ag-conflito", por_id[f"viagem-{c.pk}"]["classNames"])
        mensagens = por_id[f"viagem-{b.pk}"]["extendedProps"]["conflitos"]
        self.assertEqual(mensagens, ["ANA AGENDA também está no Ofício 12/2026 de 12/10 08:00 a 12/10 18:00 (Maringá Agenda)"])

    def test_dois_oficios_da_mesma_viagem_nao_conflitam_entre_si(self):
        viagem, oficio = self.viagem_com_oficio(quando(12, 8), quando(12, 18), servidores=[self.ana])
        irmao = Oficio.objects.create(viagem=viagem, roteiro=oficio.roteiro)
        irmao.servidores.add(self.ana)
        (ev,) = [e for e in self.eventos() if e["id"] == f"viagem-{viagem.pk}"]
        self.assertNotIn("ag-conflito", ev["classNames"])

    def test_palestra_e_viagem_da_mesma_pessoa_no_mesmo_dia(self):
        viagem, _ = self.viagem_com_oficio(quando(12, 8), quando(12, 18), servidores=[self.ana])
        palestrante = Palestrante.objects.create(nome="ANA PALESTRA", servidor=self.ana)
        palestra = DemandaEvento.objects.create(data_solicitacao=date(2026, 9, 1), solicitante="Escola", data_inicio_evento=date(2026, 10, 12))
        palestra.palestrantes.add(palestrante)
        por_id = {e["id"]: e for e in self.eventos()}
        self.assertIn("ag-conflito", por_id[f"viagem-{viagem.pk}"]["classNames"])
        self.assertIn("ag-conflito", por_id[f"demanda-{palestra.pk}"]["classNames"])
        self.assertIn("como palestrante", por_id[f"viagem-{viagem.pk}"]["extendedProps"]["conflitos"][0])

    def test_cancelada_nao_briga_com_ninguem(self):
        a, _ = self.viagem_com_oficio(quando(12, 8), quando(12, 18), servidores=[self.ana])
        b, _ = self.viagem_com_oficio(quando(12, 9), quando(12, 10), servidores=[self.ana])
        b.cancelar("teste")
        por_id = {e["id"]: e for e in self.eventos()}
        self.assertNotIn("ag-conflito", por_id[f"viagem-{a.pk}"]["classNames"])
        self.assertNotIn("ag-conflito", por_id[f"viagem-{b.pk}"]["classNames"])

    def test_dossie_da_viagem_traz_a_secao_de_conflitos_com_link(self):
        a, _ = self.viagem_com_oficio(quando(12, 8), quando(12, 18), servidores=[self.ana], numero=12)
        b, oficio_b = self.viagem_com_oficio(quando(12, 9), quando(12, 10), servidores=[self.ana], numero=13)
        self.client.force_login(self.root)
        conteudo = self.client.get(reverse("agenda:detalhe", args=["viagem", a.pk])).content.decode()
        self.assertIn("Conflitos de agenda", conteudo)
        self.assertIn("ANA AGENDA já está no Ofício 13/2026", conteudo)
        self.assertIn(reverse("viagens_oficios:editar", args=[oficio_b.pk]), conteudo)

    def test_conflitos_do_periodo_indexa_pela_chave_da_agenda(self):
        a, _ = self.viagem_com_oficio(quando(12, 8), quando(12, 18), viatura=self.viatura)
        b, _ = self.viagem_com_oficio(quando(12, 17), quando(12, 20), viatura=self.viatura)
        mapa = conflitos.conflitos_do_periodo(date(2026, 10, 1), date(2026, 11, 1))
        self.assertEqual(set(mapa), {("viagem", a.pk), ("viagem", b.pk)})
        self.assertEqual(mapa[("viagem", a.pk)][0]["recurso"], f"Viatura {self.viatura.placa_formatada}")
