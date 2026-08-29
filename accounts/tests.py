from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from auditoria.models import LogAuditoria
from solicitacoes.permissions import GRUPO_ADMINISTRADOR, GRUPO_ANALISTA

User = get_user_model()


class GestaoUsuariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("admin", password="x")
        cls.admin.groups.add(Group.objects.create(name=GRUPO_ADMINISTRADOR))
        cls.comum = User.objects.create_user("comum", password="x")

    def test_lista_exige_administrador(self):
        self.client.force_login(self.comum)
        resposta = self.client.get(reverse("accounts:usuarios_lista"))
        self.assertEqual(resposta.status_code, 403)

    def test_lista_para_administrador(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse("accounts:usuarios_lista"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "comum")

    def test_criar_usuario_com_perfil_e_senha(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse("accounts:usuarios_novo"),
            {
                "first_name": "Maria",
                "last_name": "Silva",
                "username": "maria.silva",
                "email": "maria.silva@pc.pr.gov.br",
                "perfil": GRUPO_ANALISTA,
                "senha": "SenhaForte#2026",
                "confirmacao_senha": "SenhaForte#2026",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        usuario = User.objects.get(username="maria.silva")
        self.assertTrue(usuario.groups.filter(name=GRUPO_ANALISTA).exists())
        self.assertTrue(usuario.check_password("SenhaForte#2026"))
        self.assertTrue(LogAuditoria.objects.filter(acao="USUARIO_CRIADO").exists())

    def test_criacao_exige_senha_e_confirmacao(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse("accounts:usuarios_novo"),
            {
                "first_name": "João",
                "username": "joao",
                "perfil": GRUPO_ANALISTA,
                "senha": "",
                "confirmacao_senha": "",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Defina a senha inicial")

        resposta = self.client.post(
            reverse("accounts:usuarios_novo"),
            {
                "first_name": "João",
                "username": "joao",
                "perfil": GRUPO_ANALISTA,
                "senha": "SenhaForte#2026",
                "confirmacao_senha": "Diferente#2026",
            },
        )
        self.assertContains(resposta, "As senhas não conferem")
        self.assertFalse(User.objects.filter(username="joao").exists())

    def test_senha_fraca_rejeitada(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse("accounts:usuarios_novo"),
            {
                "first_name": "Ana",
                "username": "ana",
                "perfil": GRUPO_ANALISTA,
                "senha": "12345678",
                "confirmacao_senha": "12345678",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(User.objects.filter(username="ana").exists())

    def test_editar_troca_perfil_sem_trocar_senha(self):
        self.client.force_login(self.admin)
        self.comum.groups.add(Group.objects.create(name=GRUPO_ANALISTA))
        resposta = self.client.post(
            reverse("accounts:usuarios_editar", args=[self.comum.pk]),
            {
                "first_name": "Comum",
                "username": "comum",
                "perfil": GRUPO_ADMINISTRADOR,
                "senha": "",
                "confirmacao_senha": "",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.comum.refresh_from_db()
        self.assertTrue(self.comum.groups.filter(name=GRUPO_ADMINISTRADOR).exists())
        self.assertFalse(self.comum.groups.filter(name=GRUPO_ANALISTA).exists())
        self.assertTrue(self.comum.check_password("x"))

    def test_inativar_e_reativar_usuario(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse("accounts:usuarios_alternar_ativo", args=[self.comum.pk])
        )
        self.assertEqual(resposta.status_code, 302)
        self.comum.refresh_from_db()
        self.assertFalse(self.comum.is_active)
        # Usuário inativo não consegue autenticar.
        self.assertFalse(self.client.login(username="comum", password="x"))
        self.assertTrue(LogAuditoria.objects.filter(acao="USUARIO_INATIVADO").exists())

    def test_nao_pode_inativar_a_si_mesmo(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("accounts:usuarios_alternar_ativo", args=[self.admin.pk])
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)


class AlterarSenhaTests(TestCase):
    def test_usuario_altera_a_propria_senha(self):
        usuario = User.objects.create_user("fulano", password="SenhaAntiga#1")
        self.client.force_login(usuario)
        resposta = self.client.post(
            reverse("accounts:alterar_senha"),
            {
                "old_password": "SenhaAntiga#1",
                "new_password1": "SenhaNova#2026",
                "new_password2": "SenhaNova#2026",
            },
        )
        self.assertRedirects(resposta, reverse("dashboard:index"))
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password("SenhaNova#2026"))

    def test_senha_atual_errada_reexibe_erros(self):
        usuario = User.objects.create_user("fulano", password="SenhaAntiga#1")
        self.client.force_login(usuario)
        resposta = self.client.post(
            reverse("accounts:alterar_senha"),
            {
                "old_password": "errada",
                "new_password1": "SenhaNova#2026",
                "new_password2": "SenhaNova#2026",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password("SenhaAntiga#1"))
