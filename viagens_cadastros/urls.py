from django.urls import path

from . import views
from . import estados
from . import cidades

app_name = "viagens_cadastros"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/cep/<str:cep>/", views.api_consulta_cep, name="api_consulta_cep"),
    path("cidades/", cidades.lista, name="cidades"),
    path("cidades/exportar.csv", cidades.exportar_csv, name="cidades_exportar_csv"),
    path("estados/", estados.lista, name="estados"),
    path("estados/<int:pk>/editar/", estados.editar, name="estado_editar"),
    path("estados/<int:pk>/excluir/", estados.excluir, name="estado_excluir"),
    # A tabela de diárias vem antes da rota genérica por slug: "diarias" não é
    # um cadastro do registro e não pode ser capturado por `<slug:slug>`.
    path("diarias/", views.diarias, name="diarias"),
    path("diarias/nova/", views.diaria_editar, name="diaria_nova"),
    path("diarias/<int:pk>/editar/", views.diaria_editar, name="diaria_editar"),
    path("diarias/<int:pk>/excluir/", views.diaria_excluir, name="diaria_excluir"),
    path("<slug:slug>/", views.lista, name="lista"),
    path("<slug:slug>/novo/", views.editar, name="novo"),
    path("<slug:slug>/<int:pk>/editar/", views.editar, name="editar"),
    path("<slug:slug>/<int:pk>/excluir/", views.excluir, name="excluir"),
    path("<slug:slug>/<int:pk>/padrao/", views.definir_padrao, name="definir_padrao"),
]
