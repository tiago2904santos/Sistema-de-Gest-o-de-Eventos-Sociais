"""Rotas raiz do projeto."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("conta/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("cadastros/", include("cadastros.urls")),
    path("solicitacoes/", include("solicitacoes.urls")),
    path("coffee-break/", include("coffee_break.urls")),
    path("ascom/demandas/", include("demandas_eventos.urls")),
    path("viagens/cadastros/", include("viagens_cadastros.urls")),
]
