"""m067: o painel da viagem avisa quando a equipe, o motorista ou a viatura
dos ofícios já estão em outra viagem no mesmo horário (core/conflitos.py)."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse

from viagens_oficios.models import Oficio
from viagens_oficios.tests.fixtures import CenarioOficioMixin
from viagens_roteiros.models import Roteiro
from viagens_viagem.models import Viagem


class ConflitosNoPainelTests(CenarioOficioMixin, TestCase):
    def test_painel_da_viagem_lista_conflitos_dos_oficios(self):
        viagem = Viagem.objects.create(titulo="Viagem conflito")
        oficio = self.criar()
        Oficio.objects.filter(pk=oficio.pk).update(viagem=viagem)
        irmao = Oficio.objects.create(roteiro=self.roteiro, viagem=viagem)
        irmao.servidores.add(self.a)  # da mesma viagem: não é conflito
        fora = Oficio.objects.create(roteiro=Roteiro.objects.create(
            origem_municipio=self.sede, saida_dt=self.saida + timedelta(hours=1), retorno_chegada_dt=self.saida + timedelta(hours=3)),
            viatura=self.viatura)
        conteudo = self.client.get(reverse("viagens_viagem:etapa", args=[viagem.pk, 3])).content.decode()
        self.assertIn(f"Viatura {self.viatura.placa_formatada} já está no Ofício (rascunho #{fora.pk})", conteudo)
        self.assertNotIn(f"rascunho #{irmao.pk}", conteudo)

    def test_viagem_cancelada_nao_avisa(self):
        viagem = Viagem.objects.create(titulo="Viagem cancelada")
        oficio = self.criar()
        Oficio.objects.filter(pk=oficio.pk).update(viagem=viagem)
        Oficio.objects.create(roteiro=self.roteiro, viatura=self.viatura)
        viagem.cancelar("teste")
        conteudo = self.client.get(reverse("viagens_viagem:etapa", args=[viagem.pk, 3])).content.decode()
        self.assertNotIn("já está no Ofício", conteudo)
