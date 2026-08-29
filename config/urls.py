"""Rotas raiz do projeto."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("conta/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("solicitacoes/", include("solicitacoes.urls")),
]
