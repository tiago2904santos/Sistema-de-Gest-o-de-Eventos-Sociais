from django.urls import path

from . import views

app_name = "viagens_planos"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("criar/", views.criar, name="criar"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/acao/<str:acao>/", views.acao, name="acao"),
    path("<int:pk>/calcular/", views.calcular, name="calcular"),
    path("<int:pk>/autosalvar/", views.autosalvar, name="autosalvar"),
    path("<int:pk>/eventos/adicionar/", views.evento_adicionar, name="evento_adicionar"),
    path("<int:pk>/eventos/<int:evento_pk>/editar/", views.evento_editar, name="evento_editar"),
    path("<int:pk>/eventos/<int:evento_pk>/remover/", views.evento_remover, name="evento_remover"),
    path("<int:pk>/visualizar/", views.visualizar, name="visualizar"),
    path("<int:pk>/resultados/", views.resultados, name="resultados"),
    path("<int:pk>/gerar/<str:formato>/", views.gerar, name="gerar"),
]
