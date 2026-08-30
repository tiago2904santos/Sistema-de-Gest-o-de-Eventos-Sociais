from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Estado, Municipio, OrgaoResponsavel, Regiao, TipoEvento
from solicitacoes.models import SolicitacaoEvento, StatusSolicitacao

User = get_user_model()


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user("usuario", password="x")
        cls.regiao = Regiao.objects.create(nome="Região")
        cls.estado = Estado.objects.get(codigo_ibge=41)
        cls.municipio = Municipio.objects.create(
            nome="Cidade", estado=cls.estado, regiao=cls.regiao
        )
        cls.tipo = TipoEvento.objects.create(nome="Ação social")
        cls.orgao = OrgaoResponsavel.objects.create(nome="Órgão")

    def criar(self, **kwargs):
        hoje = timezone.localdate()
        dados = {
            "data_solicitacao": hoje,
            "data_inicio_evento": hoje + timedelta(days=10),
            "data_fim_evento": hoje + timedelta(days=11),
            "municipio": self.municipio,
            "tipo_evento": self.tipo,
            "orgao_responsavel": self.orgao,
            "criado_por": self.usuario,
        }
        dados.update(kwargs)
        return SolicitacaoEvento.objects.create(**dados)

    def test_login_obrigatorio(self):
        resposta = self.client.get(reverse("dashboard:index"))
        self.assertEqual(resposta.status_code, 302)

    def test_banco_vazio_sem_erros(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("dashboard:index"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Nenhuma solicitação registrada ainda.")
        for item in resposta.context["resumo"]:
            self.assertEqual(item["valor"], 0)

    def test_metricas_reais(self):
        self.criar()
        self.criar(status=StatusSolicitacao.AGUARDANDO_DESPACHO)
        self.criar(status=StatusSolicitacao.ATENDIDA)
        self.criar(
            status=StatusSolicitacao.CANCELADA,
            data_inicio_evento=timezone.localdate() + timedelta(days=5),
        )
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("dashboard:index"))
        resumo = {item["titulo"]: item["valor"] for item in resposta.context["resumo"]}
        self.assertEqual(resumo["Solicitações no mês"], 4)
        self.assertEqual(resumo["Aguardando despacho"], 1)
        self.assertEqual(resumo["Deferidas no ano"], 1)
        # A cancelada fica fora dos eventos dos próximos 30 dias.
        self.assertEqual(resumo["Eventos nos próximos 30 dias"], 3)

    def test_ultimas_solicitacoes(self):
        criadas = [self.criar() for _ in range(7)]
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("dashboard:index"))
        ultimas = list(resposta.context["ultimas_solicitacoes"])
        self.assertEqual(len(ultimas), 5)
        self.assertEqual(ultimas[0], criadas[-1])
