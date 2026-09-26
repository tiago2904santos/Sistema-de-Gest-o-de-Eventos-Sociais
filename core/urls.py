from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("notificacoes/", views.lista_notificacoes, name="notificacoes"),
    path(
        "notificacoes/marcar-lidas/",
        views.marcar_notificacoes_lidas,
        name="notificacoes_marcar_lidas",
    ),
    path("conflitos/", views.conflitos_de_agenda, name="conflitos"),
    path("notificacoes/<int:pk>/abrir/", views.abrir_notificacao, name="notificacao_abrir"),
]
