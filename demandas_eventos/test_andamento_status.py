from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Palestrante, StatusDemanda
from .presenters import ICONES_STATUS
from .tests import BaseDemandasTestCase

MODAL = {"HTTP_X_CADASTRO_MODAL": "1"}


class AndamentoPedeOMinimoTests(BaseDemandasTestCase):
    def setUp(self):
        self.hoje = timezone.localdate()
        self.palestrante = Palestrante.objects.create(nome="Servidora Exemplo")

    def test_agendada_pede_data_e_palestrante(self):
        demanda = self.criar_demanda()
        with self.assertRaises(ValidationError) as erro:
            services.registrar_andamento(demanda, self.usuario, StatusDemanda.EVENTO_AGENDADO)
        self.assertEqual(erro.exception.messages, ["Informe a data do evento.", "Informe o palestrante."])
        demanda.refresh_from_db()
        self.assertEqual(demanda.status, StatusDemanda.PENDENTE)

        data = self.hoje + timedelta(days=10)
        services.registrar_andamento(
            demanda, self.usuario, StatusDemanda.EVENTO_AGENDADO, data_evento=data, palestrante=self.palestrante
        )
        demanda.refresh_from_db()
        self.assertEqual(demanda.status, StatusDemanda.EVENTO_AGENDADO)
        self.assertEqual(demanda.data_inicio_evento, data)
        self.assertEqual(list(demanda.palestrantes.all()), [self.palestrante])

    def test_servidor_da_planilha_vale_como_palestrante(self):
        demanda = self.criar_demanda(data_inicio_evento=self.hoje, servidor="Servidor da planilha")
        services.registrar_andamento(demanda, self.usuario, StatusDemanda.EVENTO_AGENDADO)
        self.assertEqual(demanda.status, StatusDemanda.EVENTO_AGENDADO)

    def test_atendida_pede_publico_e_so_depois_do_evento(self):
        futura = self.criar_demanda(data_inicio_evento=self.hoje + timedelta(days=3))
        opcoes = [o["valor"] for o in services.opcoes_de_status(futura, ICONES_STATUS)]
        self.assertNotIn(StatusDemanda.ATENDIDA, opcoes)
        with self.assertRaises(ValidationError) as erro:
            services.registrar_andamento(futura, self.usuario, StatusDemanda.ATENDIDA, quantidade_publico=40)
        self.assertIn("depois da data do evento", " ".join(erro.exception.messages))

        passada = self.criar_demanda(data_inicio_evento=self.hoje - timedelta(days=1))
        self.assertIn(StatusDemanda.ATENDIDA, [o["valor"] for o in services.opcoes_de_status(passada, ICONES_STATUS)])
        with self.assertRaises(ValidationError) as erro:
            services.registrar_andamento(passada, self.usuario, StatusDemanda.ATENDIDA)
        self.assertEqual(erro.exception.messages, ["Informe a quantidade de público."])
        services.registrar_andamento(passada, self.usuario, StatusDemanda.ATENDIDA, quantidade_publico=0)
        passada.refresh_from_db()
        self.assertEqual((passada.status, passada.quantidade_publico), (StatusDemanda.ATENDIDA, 0))

    def test_outros_status_nao_pedem_nada(self):
        demanda = self.criar_demanda()
        for status in (StatusDemanda.EM_ANDAMENTO, StatusDemanda.AGUARDANDO_RETORNO, StatusDemanda.CANCELADA):
            services.registrar_andamento(demanda, self.usuario, status)
            self.assertEqual(demanda.status, status)

    def test_modal_pergunta_so_o_que_falta_e_grava_junto(self):
        demanda = self.criar_demanda()
        url = reverse("demandas_eventos:andamento", args=[demanda.pk])
        self.client.force_login(self.usuario)
        resposta = self.client.get(url, **MODAL)
        for campo in ("andamento_data", "andamento_palestrante", "andamento_publico"):
            self.assertContains(resposta, f'name="{campo}"')
        resposta = self.client.post(url, {"novo_status": StatusDemanda.EVENTO_AGENDADO, "andamento_data": "2026-13-01"}, **MODAL)
        self.assertContains(resposta, "formato dd/mm/aaaa")
        resposta = self.client.post(url, {"novo_status": StatusDemanda.EVENTO_AGENDADO}, **MODAL)
        self.assertContains(resposta, "Informe a data do evento.")
        data = self.hoje + timedelta(days=5)
        resposta = self.client.post(
            url,
            {"novo_status": StatusDemanda.EVENTO_AGENDADO, "andamento_data": data.isoformat(), "andamento_palestrante": self.palestrante.pk},
            **MODAL,
        )
        self.assertEqual(resposta.json(), {"ok": True})
        demanda.refresh_from_db()
        self.assertEqual((demanda.status, demanda.data_inicio_evento), (StatusDemanda.EVENTO_AGENDADO, data))
        # Com data e palestrante, o modal só pergunta o público.
        resposta = self.client.get(url, **MODAL)
        self.assertNotContains(resposta, 'name="andamento_data"')
        self.assertNotContains(resposta, 'name="andamento_palestrante"')
        self.assertContains(resposta, 'name="andamento_publico"')

    def test_painel_conta_atendidas_pelo_ano_do_evento(self):
        ano = self.hoje.year
        # Pedida no ano passado, realizada neste ano: conta.
        self.criar_demanda(status=StatusDemanda.ATENDIDA, data_solicitacao=date(ano - 1, 12, 1), data_inicio_evento=date(ano, 1, 10))
        # Pedida neste ano, realizada no ano passado (dado da planilha): não conta.
        self.criar_demanda(status=StatusDemanda.ATENDIDA, data_solicitacao=date(ano, 1, 2), data_inicio_evento=date(ano - 1, 12, 20))
        # Sem data do evento: vale a da solicitação.
        self.criar_demanda(status=StatusDemanda.ATENDIDA, data_solicitacao=date(ano, 2, 1))
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("demandas_eventos:dashboard"))
        atendidas = next(c for c in resposta.context["resumo"] if c["titulo"] == "Atendidas no ano")
        self.assertEqual(atendidas["valor"], 2)
