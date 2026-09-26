"""Rota pública do link do fornecedor (/fornecedor/<token>/).

Namespace próprio, que NÃO é registrado no middleware de autorização por
módulo: é a única rota do Coffee Break aberta a quem não tem login, e só
responde a um token válido.
"""

from django.urls import path

from . import views_publicas

app_name = "fornecedor_publico"

urlpatterns = [
    path("<str:token>/", views_publicas.envio, name="envio"),
]
