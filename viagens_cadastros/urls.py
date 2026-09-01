from django.urls import path

from . import views

app_name = "viagens_cadastros"

urlpatterns = [
    path("", views.index, name="index"),
    # A tabela de diárias vem antes da rota genérica por slug: "diarias" não é
    # um cadastro do registro e não pode ser capturado por `<slug:slug>`.
    path("diarias/", views.diarias, name="diarias"),
    path("diarias/nova/", views.diaria_editar, name="diaria_nova"),
    path("diarias/<int:pk>/editar/", views.diaria_editar, name="diaria_editar"),
    path("<slug:slug>/", views.lista, name="lista"),
    path("<slug:slug>/novo/", views.editar, name="novo"),
    path("<slug:slug>/<int:pk>/editar/", views.editar, name="editar"),
    path(
        "<slug:slug>/<int:pk>/alternar-ativo/",
        views.alternar_ativo,
        name="alternar_ativo",
    ),
    path("<slug:slug>/<int:pk>/excluir/", views.excluir, name="excluir"),
]
