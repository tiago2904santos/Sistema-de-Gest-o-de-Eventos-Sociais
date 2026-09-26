"""m049: o cadastro de ofício avisa quando equipe, motorista ou viatura já
estão em outro compromisso no horário do roteiro (core/conflitos.py)."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse

from viagens_oficios.models import Oficio
from viagens_oficios.tests.fixtures import CenarioOficioMixin
from viagens_roteiros.models import Roteiro


class ConflitosNoOficioTests(CenarioOficioMixin, TestCase):
    def test_oficio_avisa_ao_salvar_e_na_tela_sem_bloquear(self):
        outro = Oficio.objects.create(roteiro=Roteiro.objects.create(
            origem_municipio=self.sede, saida_dt=self.saida + timedelta(hours=2), retorno_chegada_dt=self.saida + timedelta(hours=5)))
        outro.servidores.add(self.b)
        oficio = self.criar()
        conteudo = self.client.get(reverse("viagens_oficios:editar", args=[oficio.pk])).content.decode()
        self.assertIn("BRUNO TESTE já está no Ofício", conteudo)
        self.assertIn("data-conflitos", conteudo)
        resposta = self.client.post(reverse("viagens_oficios:editar", args=[oficio.pk]), self.payload(), follow=True)
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(any("Conflito de agenda: BRUNO TESTE" in str(m) for m in resposta.context["messages"]))

    def test_sem_sobreposicao_nao_ha_aviso(self):
        # O outro ofício sai no minuto em que este volta: encostar não é sobrepor.
        volta = self.roteiro.retorno_chegada_dt
        outro = Oficio.objects.create(roteiro=Roteiro.objects.create(
            origem_municipio=self.sede, saida_dt=volta, retorno_chegada_dt=volta + timedelta(hours=5)), viatura=self.viatura)
        outro.servidores.add(self.a, self.b)
        oficio = self.criar()
        conteudo = self.client.get(reverse("viagens_oficios:editar", args=[oficio.pk])).content.decode()
        self.assertNotIn("já está no Ofício", conteudo)
