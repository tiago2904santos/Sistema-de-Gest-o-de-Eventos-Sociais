from django.urls import path

from . import busca_municipios, views

app_name = "cadastros"

urlpatterns = [
    path("", views.index, name="index"),
    path("municipios/buscar/", busca_municipios.buscar_municipios, name="municipios_buscar"),
    path("<slug:slug>/", views.lista, name="lista"),
    path("<slug:slug>/novo/", views.editar, name="novo"),
    path("<slug:slug>/<int:pk>/editar/", views.editar, name="editar"),
    path("<slug:slug>/<int:pk>/alternar-ativo/", views.alternar_ativo, name="alternar_ativo"),
    path("<slug:slug>/<int:pk>/excluir/", views.excluir, name="excluir"),
]
