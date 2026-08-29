from django.contrib.auth import views as auth_views
from django.urls import path

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
]
