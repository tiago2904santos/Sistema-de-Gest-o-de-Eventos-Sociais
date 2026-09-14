from datetime import date
from decimal import Decimal

from django.urls import reverse

from auditoria.models import LogAuditoria
from .models import TabelaDiaria
from .permissions import GRUPO_GESTOR, GRUPO_OPERADOR
from .tests import BaseViagensTestCase


class ParidadeDiariasTests(BaseViagensTestCase):
    def setUp(self):
        self.gestor = self.criar_usuario("diarias_paridade", GRUPO_GESTOR)
        self.client.force_login(self.gestor)
        self.url = reverse("viagens_cadastros:diarias")
        self.dados = {"faixa": "INTERIOR", "vigencia_inicio": "2026-09-10", "valor_24h": "290.55"}

    def test_inclusao_no_historico_deriva_valores_e_preserva_vigencia_anterior(self):
        anterior = TabelaDiaria.objects.create(faixa="INTERIOR", vigencia_inicio=date(2026, 1, 1), valor_24h=Decimal("200.00"))
        resposta = self.client.post(self.url, {**self.dados, "valor_15": "999", "valor_30": "999"}, follow=True)
        self.assertContains(resposta, "Valores de Interior valendo a partir de 10/09/2026. Roteiros anteriores mantêm o valor da época.")
        nova = TabelaDiaria.objects.get(vigencia_inicio=date(2026, 9, 10))
        self.assertEqual((nova.valor_15, nova.valor_30), (Decimal("43.58"), Decimal("87.17")))
        anterior.refresh_from_db()
        self.assertEqual(anterior.valor_24h, Decimal("200.00"))
        self.assertEqual(TabelaDiaria.vigente_em("INTERIOR", date(2026, 9, 9)), anterior)
        self.assertEqual(LogAuditoria.objects.filter(usuario=self.gestor, acao="VIAGENS_DIARIA_CRIADA").count(), 1)

    def test_duplicidade_preserva_valores_e_historico_sem_criar_registro(self):
        TabelaDiaria.objects.create(faixa="INTERIOR", vigencia_inicio=date(2026, 9, 10), valor_24h=Decimal("200.00"))
        resposta = self.client.post(self.url, self.dados)
        self.assertContains(resposta, "Já existe uma vigência desta faixa nesta data.")
        self.assertContains(resposta, 'value="2026-09-10"')
        self.assertContains(resposta, 'value="290.55"')
        self.assertContains(resposta, "R$ 200,00")
        self.assertEqual(TabelaDiaria.objects.count(), 1)
        self.assertFalse(LogAuditoria.objects.filter(usuario=self.gestor, acao="VIAGENS_DIARIA_CRIADA").exists())

    def test_operador_le_historico_sem_formulario_e_post_e_recusado(self):
        self.client.force_login(self.criar_usuario("diarias_operador", GRUPO_OPERADOR))
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Só os perfis autorizados para gestão de diárias podem alterá-los.")
        self.assertNotContains(resposta, 'name="valor_24h"')
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 403)
        self.assertFalse(TabelaDiaria.objects.exists())
