from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    # Recuperação de senha por e-mail ("esqueci minha senha").
    path(
        "senha/recuperar/",
        auth_views.PasswordResetView.as_view(
            template_name="pages/auth/senha_reset.html",
            email_template_name="pages/auth/email_reset_senha.txt",
            subject_template_name="pages/auth/email_reset_senha_assunto.txt",
            success_url=reverse_lazy("accounts:senha_reset_enviado"),
        ),
        name="senha_reset",
    ),
    path(
        "senha/recuperar/enviado/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="pages/auth/senha_reset_enviado.html",
        ),
        name="senha_reset_enviado",
    ),
    path(
        "senha/recuperar/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="pages/auth/senha_reset_confirmar.html",
            success_url=reverse_lazy("accounts:senha_reset_concluido"),
        ),
        name="senha_reset_confirmar",
    ),
    path(
        "senha/recuperar/concluido/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="pages/auth/senha_reset_concluido.html",
        ),
        name="senha_reset_concluido",
    ),
    path("entrar/", views.AcessoView.as_view(), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("alterar-senha/", views.AlterarSenhaView.as_view(), name="alterar_senha"),
    # Gestão de usuários — perfil administrador.
    path("usuarios/", views.lista_usuarios, name="usuarios_lista"),
    path("usuarios/novo/", views.editar_usuario, name="usuarios_novo"),
    path("usuarios/<int:pk>/editar/", views.editar_usuario, name="usuarios_editar"),
    path(
        "usuarios/<int:pk>/alternar-ativo/",
        views.alternar_ativo_usuario,
        name="usuarios_alternar_ativo",
    ),
]
