"""Rotas raiz do projeto."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

handler403 = "core.views.erro_403"

urlpatterns = [
    path("viagens/prestacoes/", include("viagens_prestacoes.urls")),
    path("viagens/oficios/", include("viagens_oficios.urls")),
    path("viagens/termos/", include("viagens_termos.urls")),
    path("viagens/viagem/", include("viagens_viagem.urls")),
    path("viagens/ordens/", include("viagens_ordens.urls")),
    path("viagens/planos/", include("viagens_planos.urls")),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("conta/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("cadastros/", include("cadastros.urls")),
    path("solicitacoes/", include("solicitacoes.urls")),
    path("coffee-break/", include("coffee_break.urls")),
    path("ascom/demandas/", include("demandas_eventos.urls")),
    path("ascom/publicacoes/", include("publicacoes.urls")),
    path("ascom/imprensa/", include("atendimento_imprensa.urls")),
    # Entrada amigável do módulo: /viagens/ leva à tela principal (Roteiros).
    path(
        "viagens/",
        RedirectView.as_view(pattern_name="viagens_roteiros:lista"),
        name="viagens_entrada",
    ),
    path("viagens/cadastros/", include("viagens_cadastros.urls")),
    path("viagens/roteiros/", include("viagens_roteiros.urls")),
    path("documentos/", include("documentos.urls")),
    path("assistente/", include("assistente.urls")),
]
