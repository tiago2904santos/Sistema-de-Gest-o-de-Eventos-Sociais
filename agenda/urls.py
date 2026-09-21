from django.urls import path

from . import views

app_name = "agenda"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("eventos/", views.eventos, name="eventos"),
    path("detalhe/<str:fonte>/<int:pk>/", views.detalhe, name="detalhe"),
]
