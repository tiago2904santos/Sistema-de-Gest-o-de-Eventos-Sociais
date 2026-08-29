from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path(
        "entrar/",
        auth_views.LoginView.as_view(
            template_name="pages/auth/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
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
