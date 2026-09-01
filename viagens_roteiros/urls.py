from django.urls import path

from . import views

app_name = "viagens_roteiros"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.editar, name="novo"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/calcular/", views.calcular, name="calcular"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("<int:pk>/reativar/", views.reativar, name="reativar"),
    path("<int:pk>/excluir/", views.excluir, name="excluir"),
]
