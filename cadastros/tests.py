from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from auditoria.models import LogAuditoria
from solicitacoes.permissions import GRUPO_ADMINISTRADOR

from .models import Municipio, Regiao, TipoEvento

User = get_user_model()


class SeedTests(TestCase):
    def test_seed_e_idempotente(self):
        call_command("seed_initial_data")
        totais = (
            Group.objects.count(),
            TipoEvento.objects.count(),
            Municipio.objects.count(),
            Regiao.objects.count(),
        )
        call_command("seed_initial_data")
        self.assertEqual(
            totais,
            (
                Group.objects.count(),
                TipoEvento.objects.count(),
                Municipio.objects.count(),
                Regiao.objects.count(),
            ),
        )
        self.assertTrue(Group.objects.filter(name=GRUPO_ADMINISTRADOR).exists())


class CrudCadastrosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.comum = User.objects.create_user("comum", password="x")
        cls.admin = User.objects.create_user("admin", password="x")
        cls.admin.groups.add(Group.objects.create(name=GRUPO_ADMINISTRADOR))

    def test_usuario_comum_nao_acessa(self):
        self.client.force_login(self.comum)
        resposta = self.client.get(reverse("cadastros:index"))
        self.assertEqual(resposta.status_code, 403)

    def test_administrador_cria_edita_e_inativa(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse("cadastros:index"))
        self.assertEqual(resposta.status_code, 200)

        resposta = self.client.post(
            reverse("cadastros:novo", args=["tipos-evento"]), {"nome": "Novo tipo"}
        )
        self.assertEqual(resposta.status_code, 302)
        tipo = TipoEvento.objects.get(nome="Novo tipo")

        resposta = self.client.post(
            reverse("cadastros:editar", args=["tipos-evento", tipo.pk]),
            {"nome": "Tipo renomeado"},
        )
        self.assertEqual(resposta.status_code, 302)
        tipo.refresh_from_db()
        self.assertEqual(tipo.nome, "Tipo renomeado")

        resposta = self.client.post(
            reverse("cadastros:alternar_ativo", args=["tipos-evento", tipo.pk])
        )
        tipo.refresh_from_db()
        self.assertFalse(tipo.ativo)

        # Cada ação administrativa gera auditoria.
        self.assertEqual(LogAuditoria.objects.count(), 3)

    def test_validacao_no_form(self):
        self.client.force_login(self.admin)
        TipoEvento.objects.create(nome="Duplicado")
        resposta = self.client.post(
            reverse("cadastros:novo", args=["tipos-evento"]), {"nome": "Duplicado"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "form-erro")
