"""Rotas públicas do pedido de palestra (/pedido/).

Namespace próprio, que NÃO é registrado no middleware de autorização por
módulo: estas são as únicas rotas do app abertas a quem não tem login.
"""

from django.urls import path

from . import views_publicas

app_name = "pedido_publico"

urlpatterns = [
    path("", views_publicas.pedido, name="pedido"),
    path("recebido/", views_publicas.recebido, name="recebido"),
    path("acompanhar/<str:token>/", views_publicas.acompanhar, name="acompanhar"),
]
