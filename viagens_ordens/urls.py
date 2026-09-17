from django.urls import path

from . import views

app_name = "viagens_ordens"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("api/oficios/", views.api_buscar_oficios, name="api_buscar_oficios"),
    path("documentos/<uuid:pk>/assinatura/", views.assinatura_artefato, name="assinatura_artefato"),
    path("nova/", views.editar, name="novo"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/acao/<str:acao>/", views.acao, name="acao"),
    path("<int:pk>/gerar/<str:formato>/", views.gerar, name="gerar"),
]
