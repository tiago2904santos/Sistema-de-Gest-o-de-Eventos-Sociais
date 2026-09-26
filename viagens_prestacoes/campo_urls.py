"""Rotas públicas do diário no celular (m096): o link do motorista, sem login.

Ficam num namespace próprio, fora de `viagens_prestacoes`, para não herdar a
exigência de login e de módulo — o acesso é o token do link, e ele só alcança
aquele diário.
"""

from django.urls import path

from . import campo_views

app_name = "campo_diario"
urlpatterns = [
    path("sw.js", campo_views.service_worker, name="sw"),
    path("<str:token>/", campo_views.pagina, name="pagina"),
    path("<str:token>/enviar/", campo_views.sincronizar, name="enviar"),
    path("<str:token>/manifest.webmanifest", campo_views.manifest, name="manifest"),
]
