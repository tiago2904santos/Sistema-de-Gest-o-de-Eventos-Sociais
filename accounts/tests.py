import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from auditoria.models import LogAuditoria
from solicitacoes.permissions import GRUPO_ADMINISTRADOR, GRUPO_GESTOR_DG, GRUPO_SOLICITANTE

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

    def test_gestor_dg_tambem_gerencia_usuarios(self):
        gestor = User.objects.create_user("gestor", password="x")
        gestor.groups.add(Group.objects.create(name=GRUPO_GESTOR_DG))
        self.client.force_login(gestor)
        resposta = self.client.get(reverse("accounts:usuarios_lista"))
        self.assertEqual(resposta.status_code, 200)

    def test_criar_usuario_com_perfil_e_senha(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse("accounts:usuarios_novo"),
            {
                "first_name": "Maria",
                "last_name": "Silva",
                "username": "maria.silva",
                "email": "maria.silva@pc.pr.gov.br",
                "perfil": GRUPO_SOLICITANTE,
                "senha": "SenhaForte#2026",
                "confirmacao_senha": "SenhaForte#2026",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        usuario = User.objects.get(username="maria.silva")
        self.assertTrue(usuario.groups.filter(name=GRUPO_SOLICITANTE).exists())
        self.assertTrue(usuario.check_password("SenhaForte#2026"))
        self.assertTrue(LogAuditoria.objects.filter(acao="USUARIO_CRIADO").exists())

    def test_criacao_exige_senha_e_confirmacao(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse("accounts:usuarios_novo"),
            {
                "first_name": "João",
                "username": "joao",
                "perfil": GRUPO_SOLICITANTE,
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
                "perfil": GRUPO_SOLICITANTE,
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
                "perfil": GRUPO_SOLICITANTE,
                "senha": "12345678",
                "confirmacao_senha": "12345678",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(User.objects.filter(username="ana").exists())

    def test_editar_troca_perfil_sem_trocar_senha(self):
        self.client.force_login(self.admin)
        self.comum.groups.add(Group.objects.create(name=GRUPO_SOLICITANTE))
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
        self.assertFalse(self.comum.groups.filter(name=GRUPO_SOLICITANTE).exists())
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


class TrocaObrigatoriaDeSenhaTests(TestCase):
    """Senha cadastrada por outra pessoa vale só até o primeiro acesso."""

    def setUp(self):
        self.usuario = User.objects.create_user("fulano", password="SenhaInicial#1")
        self.usuario.deve_trocar_senha = True
        self.usuario.save(update_fields=["deve_trocar_senha"])
        self.client.force_login(self.usuario)

    def test_navegacao_e_desviada_para_a_troca(self):
        resposta = self.client.get(reverse("dashboard:index"))
        self.assertRedirects(resposta, reverse("accounts:alterar_senha"))

    def test_pagina_de_troca_continua_acessivel(self):
        resposta = self.client.get(reverse("accounts:alterar_senha"))
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["troca_obrigatoria"])

    def test_apos_trocar_a_navegacao_e_liberada(self):
        self.client.post(
            reverse("accounts:alterar_senha"),
            {
                "old_password": "SenhaInicial#1",
                "new_password1": "SenhaMinha#2026",
                "new_password2": "SenhaMinha#2026",
            },
        )
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.deve_trocar_senha)
        self.assertEqual(
            self.client.get(reverse("dashboard:index")).status_code, 200
        )

    def test_usuario_criado_pelo_admin_nasce_com_a_marca(self):
        admin = User.objects.create_user("chefe", password="x", is_superuser=True)
        admin.is_staff = True
        admin.save()
        self.client.force_login(admin)
        self.client.post(
            reverse("accounts:usuarios_novo"),
            {
                "first_name": "Novato",
                "username": "novato",
                "email": "novato@pc.pr.gov.br",
                "perfil": GRUPO_SOLICITANTE,
                "senha": "SenhaInicial#9",
                "confirmacao_senha": "SenhaInicial#9",
            },
        )
        self.assertTrue(User.objects.get(username="novato").deve_trocar_senha)


class RecuperacaoSenhaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user(
            "fulano", password="senha-antiga", email="fulano@pc.pr.gov.br"
        )

    def test_link_esqueci_senha_na_tela_de_login(self):
        resposta = self.client.get(reverse("accounts:login"))
        self.assertContains(resposta, "Esqueci minha senha")
        self.assertContains(resposta, reverse("accounts:senha_reset"))

    def test_fluxo_completo_de_recuperacao(self):
        resposta = self.client.post(
            reverse("accounts:senha_reset"), {"email": "fulano@pc.pr.gov.br"}
        )
        self.assertRedirects(resposta, reverse("accounts:senha_reset_enviado"))
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Recuperação de senha", email.subject)
        self.assertIn("fulano", email.body)

        link = re.search(r"/conta/senha/recuperar/[^/]+/[^/\s]+/", email.body)
        self.assertIsNotNone(link, email.body)

        # O primeiro acesso redireciona para a URL interna com o token na sessão.
        resposta = self.client.get(link.group(0), follow=True)
        self.assertEqual(resposta.status_code, 200)
        url_definir = resposta.request["PATH_INFO"]

        resposta = self.client.post(
            url_definir,
            {
                "new_password1": "NovaSenha!2026",
                "new_password2": "NovaSenha!2026",
            },
        )
        self.assertRedirects(resposta, reverse("accounts:senha_reset_concluido"))
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("NovaSenha!2026"))

    def test_email_desconhecido_nao_envia_nem_revela(self):
        resposta = self.client.post(
            reverse("accounts:senha_reset"), {"email": "naoexiste@pc.pr.gov.br"}
        )
        # Mesma resposta de sucesso (não revela quais e-mails existem)...
        self.assertRedirects(resposta, reverse("accounts:senha_reset_enviado"))
        # ...mas nenhum e-mail sai.
        self.assertEqual(len(mail.outbox), 0)
