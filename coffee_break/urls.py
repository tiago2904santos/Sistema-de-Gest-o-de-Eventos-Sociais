from django.urls import path

from . import views

app_name = "coffee_break"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("lotes/", views.lista_lotes, name="lotes"),
    path("lotes/<int:pk>/", views.detalhe_lote, name="lote_detalhe"),
    path("solicitacoes/", views.lista_solicitacoes, name="solicitacoes"),
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
