from django.urls import path

from . import views

app_name = "atendimento_imprensa"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("atendimentos/", views.lista, name="lista"),
    path("atendimentos/exportar/", views.exportar, name="exportar"),
    path("atendimentos/novo/", views.novo, name="novo"),
    # "Preencher com um e-mail" da tela nova: lê e sugere, não grava (POST, JSON).
    path("atendimentos/novo/ler-email/", views.ler_email, name="ler_email"),
    path("atendimentos/<int:pk>/editar/", views.editar, name="editar"),
    path("atendimentos/<int:pk>/andamento/", views.registrar_andamento, name="andamento"),
    path("cadastros/", views.cadastros, name="cadastros"),
    path("cadastros/<str:tipo>/", views.lista_cadastro, name="cadastro_lista"),
    path("cadastros/<str:tipo>/novo/", views.editar_cadastro, name="cadastro_novo"),
    path(
        "cadastros/<str:tipo>/<int:pk>/editar/",
        views.editar_cadastro,
        name="cadastro_editar",
    ),
    path(
        "cadastros/<str:tipo>/<int:pk>/excluir/",
        views.excluir_cadastro,
        name="cadastro_excluir",
    ),
]
