"""A situação real das viagens na Agenda (m131): a mesma da lista de Viagens."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from viagens_cadastros.models import Servidor
from viagens_oficios.models import Oficio
from viagens_prestacoes.models import PrestacaoContas, PrestacaoServidor
from viagens_viagem.models import Viagem

User = get_user_model()


class SituacaoDaViagemNaAgenda(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser("root_situacao", "root_situacao@example.com", None)

    def setUp(self):
        self.client.force_login(self.root)

    def viagem(self, **campos):
        dados = {"titulo": "Teste", "data_inicio": date(2026, 9, 10), "data_fim": date(2026, 9, 12)}
        dados.update(campos)
        return Viagem.objects.create(**dados)

    def evento(self, viagem):
        lista = self.client.get(reverse("agenda:eventos"), {"start": "2026-09-01", "end": "2026-10-01", "fontes": "viagem"}).json()
        (ev,) = [e for e in lista if e["id"] == f"viagem-{viagem.pk}"]
        return ev

    def test_viagem_com_todas_as_prestacoes_finalizadas_aparece_como_finalizado(self):
        viagem = self.viagem()
        oficio = Oficio.objects.create(viagem=viagem, numero=5, ano=2026, status=Oficio.STATUS_FINALIZADO)
        prestacao, _ = PrestacaoContas.objects.get_or_create(oficio=oficio)
        PrestacaoServidor.objects.create(prestacao=prestacao, servidor=Servidor.objects.create(nome="ANA FIM"), finalizada=True)
        # O campo status continua "rascunho": é ele que a Agenda não pode mais ler.
        self.assertEqual(viagem.status, Viagem.STATUS_RASCUNHO)

        ev = self.evento(viagem)
        self.assertEqual(ev["extendedProps"]["situacao"], "Finalizado")
        self.assertEqual(ev["extendedProps"]["situacao_slug"], "finalizado")
        self.assertIn("ag-sit-finalizado", ev["classNames"])

        dossie = self.client.get(reverse("agenda:detalhe", args=["viagem", viagem.pk])).content.decode()
        self.assertIn(">Finalizado<", dossie)
        self.assertIn("st--atendido", dossie)

    def test_viagem_sem_documentos_e_rascunho_e_cancelada_e_cancelado(self):
        rascunho = self.viagem()
        cancelada = self.viagem(titulo="Cancelada")
        cancelada.cancelar("teste")
        self.assertEqual(self.evento(rascunho)["extendedProps"]["situacao"], "Rascunho")
        ev = self.evento(cancelada)
        self.assertEqual(ev["extendedProps"]["situacao"], "Cancelado")
        self.assertTrue(ev["extendedProps"]["encerrado"])
