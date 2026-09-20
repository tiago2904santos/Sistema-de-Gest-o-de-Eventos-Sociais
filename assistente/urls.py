from django.urls import path

from . import views

app_name = "assistente"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("enviar/", views.enviar, name="enviar"),
    path("nova/", views.nova_conversa, name="nova"),
]
