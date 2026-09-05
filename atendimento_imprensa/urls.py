from django.urls import path

from . import views

app_name = "atendimento_imprensa"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("atendimentos/", views.lista, name="lista"),
    path("atendimentos/exportar/", views.exportar, name="exportar"),
    path("atendimentos/novo/", views.novo, name="novo"),
    path("atendimentos/<int:pk>/", views.detalhe, name="detalhe"),
    path("atendimentos/<int:pk>/editar/", views.editar, name="editar"),
    path("cadastros/", views.cadastros, name="cadastros"),
    path("cadastros/<str:tipo>/", views.lista_cadastro, name="cadastro_lista"),
    path("cadastros/<str:tipo>/novo/", views.editar_cadastro, name="cadastro_novo"),
    path(
        "cadastros/<str:tipo>/<int:pk>/editar/",
        views.editar_cadastro,
        name="cadastro_editar",
    ),
    path(
        "cadastros/<str:tipo>/<int:pk>/alternar/",
        views.alternar_cadastro,
        name="cadastro_alternar",
    ),
]
