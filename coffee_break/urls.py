from django.urls import path

from . import views

app_name = "coffee_break"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("cadastros/", views.cadastros, name="cadastros"),
    path("cadastros/<str:tipo>/", views.lista_cadastro, name="cadastro_lista"),
    path(
        "cadastros/<str:tipo>/novo/",
        views.editar_cadastro,
        name="cadastro_novo",
    ),
    path(
        "cadastros/<str:tipo>/<int:pk>/editar/",
        views.editar_cadastro,
        name="cadastro_editar",
    ),
    path("lotes/", views.lista_lotes, name="lotes"),
    path("lotes/<int:pk>/", views.detalhe_lote, name="lote_detalhe"),
    path("solicitacoes/", views.lista_solicitacoes, name="solicitacoes"),
    path("solicitacoes/exportar/", views.exportar_solicitacoes, name="exportar"),
    path("solicitacoes/nova/", views.nova_solicitacao, name="nova"),
    path("solicitacoes/<int:pk>/", views.detalhe_solicitacao, name="detalhe"),
    path("solicitacoes/<int:pk>/editar/", views.editar_solicitacao, name="editar"),
    # Mudanças de estado — somente POST, com CSRF.
    path(
        "solicitacoes/<int:pk>/cancelar/",
        views.cancelar_solicitacao,
        name="cancelar",
    ),
    path(
        "solicitacoes/<int:pk>/reativar/",
        views.reativar_solicitacao,
        name="reativar",
    ),
]
